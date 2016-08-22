import logging

from py_expression_eval import Parser
from voluptuous import All, Any, Coerce, Length, Optional, Required, Schema


log = logging.getLogger('app.response_type')

response_parts_schema = Schema([
    {
        # Common fields
        Required('id', default=None): Any(
            All(str, Length(min=1)), None),
        'type': Any('multiple_choice', 'numerical'),
        Required('name', default=None): Any(
            All(str, Length(min=1)), None),
        Required('description', default=None): Any(
            All(str, Length(min=1)), None),
        # Fields that vary by type
        # Multiple choice
        Optional('options'): All([
            {
                'score': Coerce(float),
                'name': All(str, Length(min=1)),
                Required('if', default=None): Any(
                    All(str, Length(min=1)), None),
                Required('description', default=None): Any(
                    All(str, Length(min=1)), None)
            }
        ], Length(min=2)),
        # Numerical
        Optional('lower'): Any(All(str, Length(min=1)), None),
        Optional('upper'): Any(All(str, Length(min=1)), None),
    },
], required=True)


response_schema = Schema([
    Any(
        {
            'index': int,
            'note': All(str, Length(min=1)),
        },
        {
            'value': Coerce(float),
        },
    )
], required=True)


class ResponseTypeError(Exception):
    pass


class ExpressionError(ResponseTypeError):
    '''Error in response type definition'''
    pass


class ResponseError(ResponseTypeError):
    '''Error in user-provided response'''
    pass


# These functions are used to calculate scores and validate entered data.
# NOTE: keep changes made to these classes in sync with those in response.js.


parser = Parser()


def unique_strings(ss):
    return sorted(set(ss))


def parse(exp):
    try:
        return parser.parse(exp) if exp else None
    except Exception as e:
        raise ExpressionError("'%s': %s" % (exp, e))


def refs(c_exp):
    return c_exp.variables() if c_exp else []


class ResponseType:
    def __init__(self, name, parts_def, formula):
        self.name = name
        self.parts = [response_part(p_def) for p_def in parts_def]
        self.formula = parse(formula)
        self.declared_vars = unique_strings([
            v for part in self.parts
            for v in part.declared_vars])
        self.free_vars = unique_strings([
            v for part in self.parts
            for v in part.free_vars] + refs(self.formula))
        self.unbound_vars = unique_strings([
            v for v in self.free_vars
            if v not in self.declared_vars])

    def score(self, response_parts, scope):
        if self.formula is not None:
            try:
                return self.formula.evaluate(scope)
            except Exception as e:
                raise ExpressionError(str(e))

        score = 0.0
        for part_t, part_r in zip(self.parts, response_parts):
            try:
                score += part_t.score(part_r)
            except Exception as e:
                i = self.parts.index(part_t)
                raise ResponseError(
                    "Response part %d is invalid: %s" % (i, e))
        return score

    def variables(self, response_parts, ignore_errors=False):
        scope = {}
        for part_t, part_r in zip(self.parts, response_parts):
            try:
                scope.update(part_t.variables(part_r))
            except Exception as e:
                if ignore_errors:
                    i = self.parts.index(part_t)
                    raise ResponseError(
                        "Response part %d is invalid: %s" % (i, e))
        return scope

    def validate(self, response_parts, scope):
        for i, (part_t, part_r) in enumerate(zip(self.parts, response_parts)):
            try:
                part_t.validate(part_r, scope)
            except Exception as e:
                if part_t.name:
                    name = part_t.name
                    if len(self.parts) > 1:
                        name += " (part %d)" % (i + 1)
                else:
                    if len(self.parts) > 1:
                        name = "Response part %d" % (i + 1)
                    else:
                        name = "Response"
                raise ResponseError(
                    "%s is invalid: %s" % (name, e))

    def calculate_score(self, response_parts):
        if response_parts is None or len(response_parts) != len(self.parts):
            raise ResponseError("Response is incomplete")

        scope = self.variables(response_parts)
        self.validate(response_parts, scope)
        return self.score(response_parts, scope)

    def __repr__(self):
        return "ResponseType(%s)" % (self.name)


def response_part(p_def):
    if p_def['type'] == 'multiple_choice':
        return MultipleChoice(p_def)
    else:
        return Numerical(p_def)


class ResponsePart:
    def __init__(self, p_def):
        self.id_ = p_def.get('id')
        self.name = p_def.get('name')
        self.type = p_def['type']
        self.description = p_def.get('description')


class MultipleChoice(ResponsePart):
    def __init__(self, p_def):
        super().__init__(p_def)
        self.options = [ResponseOption(o_def)
                        for o_def in p_def['options']]
        self.declared_vars = [self.id_, self.id_ + '__i'] if self.id_ else []
        self.free_vars = unique_strings([
            v for opt in self.options
            for v in opt.free_vars])

    def get_option(self, part_r):
        try:
            i = part_r['index']
        except KeyError:
            raise ResponseError("No index specified")
        if i < 0:
            raise IndexError("Option %d does not exist" % i)
        option = self.options[i]
        return i, option

    def score(self, part_r):
        _, option = self.get_option(part_r)
        return option.score

    def variables(self, part_r):
        variables = {}
        if self.id_:
            i, option = self.get_option(part_r)
            variables[self.id_] = option.score
            variables[self.id_ + '__i'] = i
        return variables

    def validate(self, part_r, scope):
        _, option = self.get_option(part_r)
        if not option.available(scope):
            raise ResponseError(
                "Conditions for option '%s' are not met" % option.name)

    def __repr__(self):
        return "MultipleChoice(%s)" % (self.name or self.id_)


class ResponseOption:
    def __init__(self, o_def):
        self.score = o_def['score']
        self.name = o_def['name']
        self.predicate = parse(o_def.get('if'))
        self.free_vars = refs(self.predicate)

    def available(self, scope):
        if not self.predicate:
            return True

        try:
            return bool(self.predicate.evaluate(scope))
        except Exception:
            return False

    def __repr__(self):
        return "ResponseOption(%s: %f)" % (self.name, self.score)


class Numerical(ResponsePart):
    def __init__(self, p_def):
        super().__init__(p_def)
        self.lower_exp = parse(p_def.get('lower'))
        self.upper_exp = parse(p_def.get('upper'))
        self.declared_vars = [self.id_] if self.id_ else []
        self.free_vars = unique_strings(
            refs(self.lower_exp) + refs(self.upper_exp))

    def score(self, part_r):
        try:
            return part_r['value']
        except KeyError:
            raise ResponseError("No value specified")

    def variables(self, part_r):
        variables = {}
        if self.id_:
            variables[self.id_] = part_r['value']
        return variables;

    def lower(self, scope):
        if not self.lower_exp:
            return float('-inf')
        try:
            return self.lower_exp.evaluate(scope)
        except Exception as e:
            log.debug('Could not evaluate lower_exp: %s: %s',
                      self.lower_exp.toString(), e)
            raise ExpressionError(str(e))

    def upper(self, scope):
        if not self.upper_exp:
            return float('inf')
        try:
            return self.upper_exp.evaluate(scope)
        except Exception as e:
            log.debug('Could not evaluate upper_exp: %s: %s',
                      self.upper_exp.toString(), e)
            raise ExpressionError(str(e))

    def validate(self, part_r, scope):
        score = self.score(part_r)
        if self.lower(scope) > score:
            raise ResponseError("Value must be greater than %s" %
                                self.lower(scope))
        if self.upper(scope) < score:
            raise ResponseError("Value must be less than %s" %
                                self.upper(scope))

    def __repr__(self):
        return "Numerical(%s)" % (self.name or self.id_)
