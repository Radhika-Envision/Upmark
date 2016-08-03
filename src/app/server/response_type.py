
import logging

from simpleeval import simple_eval, InvalidExpression


log = logging.getLogger('app.response_type')


class ResponseTypeError(Exception):
    pass


class ExpressionError(ResponseTypeError):
    '''Error in response type definition'''
    pass


class ResponseError(ResponseTypeError):
    '''Error in user-provided response'''
    pass


class ResponseTypeCache:
    def __init__(self, rt_defs):
        self.rt_defs = rt_defs
        self.materialised_types = {}

    def __getitem__(self, id_):
        if id_ not in self.materialised_types:
            for rt_def in self.rt_defs:
                if rt_def['id'] == id_:
                    self.materialised_types[id_] = ResponseType(rt_def)
                    break
        return self.materialised_types[id_]

# Important: keep changes made to these classes in sync with those in
# response.js.

class ResponseType:
    def __init__(self, rt_def):
        self.id_ = rt_def['id']
        self.name = rt_def['name']
        self.parts = [response_part(p_def) for p_def in rt_def['parts']]
        self.formula = rt_def.get('formula', None)

    def score(self, response_parts, scope):
        if self.formula is not None:
            try:
                return simple_eval(self.formula, names=scope)
            except InvalidExpression as e:
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
        return "ResponseType(%s)" % (self.name or self.id_)


def response_part(p_def):
    if p_def['type'] == 'multiple_choice':
        return MultipleChoice(p_def)
    else:
        return Numerical(p_def)


class ResponsePart:
    def __init__(self, p_def):
        self.id_ = p_def.get('id', None)
        self.name = p_def.get('name', None)
        self.description = p_def.get('description', None)


class MultipleChoice(ResponsePart):
    def __init__(self, p_def):
        super().__init__(p_def)
        self.options = [ResponseOption(o_def)
                        for o_def in p_def['options']]

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
        self.predicate = o_def.get('if', None)

    def available(self, scope):
        if not self.predicate:
            return True

        try:
            return bool(simple_eval(self.predicate, names=scope))
        except Exception:
            return False

    def __repr__(self):
        return "ResponseOption(%s: %f)" % (self.name, self.score)


class Numerical(ResponsePart):
    def __init__(self, p_def):
        super().__init__(p_def)
        self.lower_exp = p_def.get('lower')
        self.upper_exp = p_def.get('upper')

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
            return simple_eval(self.lower_exp, names=scope)
        except (InvalidExpression, TypeError) as e:
            log.debug('Could not evaulate lower_exp: %s: %s', self.lower_exp, e)
            raise ExpressionError(str(e))

    def upper(self, scope):
        if not self.upper_exp:
            return float('inf')
        try:
            return simple_eval(self.upper_exp, names=scope)
        except (InvalidExpression, TypeError) as e:
            log.debug('Could not evaulate upper_exp: %s: %s', self.upper_exp, e)
            raise ExpressionError(str(e))

    def validate(self, part_r, scope):
        score = self.score(part_r)
        if self.lower(scope) > score:
            raise ResponseError("Value must be greater than %s" % self.lower(scope))
        if self.upper(scope) < score:
            raise ResponseError("Value must be less than %s" % self.upper(scope))

    def __repr__(self):
        return "Numerical(%s)" % (self.name or self.id_)
