
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
        self.parts = [ResponsePart(p_def) for p_def in rt_def['parts']]
        self.formula = rt_def.get('formula', None)

    def calculate_score(self, response):
        if not response or len(response) != len(self.parts):
            raise ResponseError("Response is incomplete")

        score = 0.0
        variables = {}
        options = []

        # First pass: gather variables and calculate_score
        for i, (part_t, part) in enumerate(zip(self.parts, response)):
            try:
                part_index = part['index']
            except KeyError:
                raise ResponseError(
                    "Response is missing index for part %d" % (i + 1))

            try:
                if part_index < 0:
                    raise IndexError()
                option = part_t.options[part_index]
            except IndexError:
                raise ResponseError(
                    "Response part %d is out of range" % (i + 1))

            options.append(option)
            if part_t.id_ is not None:
                variables[part_t.id_] = option.score
                variables[part_t.id_ + '__i'] = part_index

            # Default is sum of all parts; may be overridden by custom formula
            score += option.score

        # Second pass: validate options according to predicates
        for i, option in enumerate(options):
            if option.predicate is not None:
                try:
                    enabled = simple_eval(option.predicate, names=variables)
                except InvalidExpression as e:
                    raise ExpressionError(str(e))
                if not bool(enabled):
                    raise ResponseError(
                        "Response part %d is invalid: conditions for option "
                        "'%s' are not met" % (i + 1, option.name))

        if self.formula is not None:
            try:
                score = simple_eval(self.formula, names=variables)
            except InvalidExpression as e:
                raise ExpressionError(str(e))

        return score

    def __repr__(self):
        return "ResponseType(%s)" % (self.name or self.id_)


class ResponsePart:
    def __init__(self, p_def):
        self.id_ = p_def.get('id', None)
        self.name = p_def.get('name', None)
        self.description = p_def.get('description', None)
        self.options = [ResponseOption(o_def)
                        for o_def in p_def['options']]

    def __repr__(self):
        return "ResponsePart(%s)" % (self.name or self.id_)


class ResponseOption:
    def __init__(self, o_def):
        self.score = o_def['score']
        self.name = o_def['name']
        self.predicate = o_def.get('if', None)

    def __repr__(self):
        return "ResponseOption(%s: %f)" % (self.name, self.score)
