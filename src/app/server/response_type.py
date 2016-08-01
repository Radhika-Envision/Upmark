
from simpleeval import simple_eval, InvalidExpression


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


class ResponseType:
    def __init__(self, rt_def):
        self.id_ = rt_def['id']
        self.name = rt_def['name']
        self.parts = [response_part(p_def) for p_def in rt_def['parts']]
        self.formula = rt_def.get('formula', None)

    def calculate_score(self, response):
        if response is None or len(response) != len(self.parts):
            raise ResponseError("Response is incomplete")

        score = 0.0
        scope = {}
        options = []

        # First pass: gather variables and calculate_score
        for i, (part_t, part) in enumerate(zip(self.parts, response)):
            try:
                score += part_t.score(part)
                scope.update(part_t.variables(part))
            except Exception as e:
                raise ResponseError(
                    "Response part %d is invalid: %s" % (i, e))

        for i, (part_t, part) in enumerate(zip(self.parts, response)):
            try:
                part_t.validate(part, scope)
            except Exception as e:
                raise ResponseError(
                    "Response part %d is invalid: %s" % (i, e))

        if self.formula is not None:
            try:
                score = simple_eval(self.formula, names=scope)
            except InvalidExpression as e:
                raise ExpressionError(str(e))

        return score

    def __repr__(self):
        return "ResponseType(%s)" % (self.name or self.id_)


def response_part(p_def):
    if 'options' in p_def:
        return MultipleChoice(p_def)
    else:
        return Numerical(p_def)


class ResponsePart:
    def __init__(self, p_def):
        self.id_ = p_def.get('id', None)
        self.name = p_def.get('name', None)
        self.description = p_def.get('description', None)

    def score(self, part):
        return 0

    def variables(self, part):
        return {}

    def validate(self, part, scope):
        pass


class MultipleChoice(ResponsePart):
    def __init__(self, p_def):
        super().__init__(p_def)
        self.options = [ResponseOption(o_def)
                        for o_def in p_def['options']]

    def get_option(self, part):
        i = part['index']
        if i < 0:
            raise IndexError("Option %d does not exist" % i)
        option = self.options[i]
        return i, option

    def score(self, part):
        _, option = self.get_option(part)
        return option.score

    def variables(self, part):
        if self.id_ is None:
            return {}
        i, option = self.get_option(part)
        return {
            self.id_: option.score,
            self.id_ + '__i': i,
        }

    def validate(self, part, scope):
        i, option = self.get_option(part)
        if not option.predicate:
            return

        try:
            enabled = simple_eval(option.predicate, names=scope)
        except InvalidExpression as e:
            raise ExpressionError(str(e))

        if not bool(enabled):
            raise ResponseError(
                "Conditions for option '%s' are not met" % option.name)

    def __repr__(self):
        return "MultipleChoice(%s)" % (self.name or self.id_)


class ResponseOption:
    def __init__(self, o_def):
        self.score = o_def['score']
        self.name = o_def['name']
        self.predicate = o_def.get('if', None)

    def __repr__(self):
        return "ResponseOption(%s: %f)" % (self.name, self.score)


class Numerical(ResponsePart):
    def __init__(self, p_def):
        super().__init__(p_def)
        self.lower = p_def.get('lower')
        self.upper = p_def.get('upper')

    def score(self, part):
        return part['value']

    def variables(self, part):
        return {
            self.id_: part['value'],
        }

    def validate(self, part, scope):
        if self.lower is None and self.upper is None:
            return

        if isinstance(self.lower, str):
            try:
                lower = simple_eval(self.lower, names=scope)
            except InvalidExpression as e:
                raise ExpressionError(str(e))
        else:
            lower = self.lower

        if isinstance(self.upper, str):
            try:
                upper = simple_eval(self.upper, names=scope)
            except InvalidExpression as e:
                raise ExpressionError(str(e))
        else:
            upper = self.upper

        score = self.score(part)
        if lower is not None and lower > score:
            raise ResponseError("Value must be greater than %s" % lower)
        if upper is not None and upper < score:
            raise ResponseError("Value must be less than %s" % upper)

    def __repr__(self):
        return "Numerical(%s)" % (self.name or self.id_)
