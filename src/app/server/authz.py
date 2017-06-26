import re


class Policy:
    def __init__(self):
        self.rules = {}
        self.context = {}
        self.context['_authz'] = lambda ruleName: self._check(ruleName)

    def declare(self, decl):
        rule = Rule(decl['name'], decl['description'], decl['rule'])
        self.rules[rule.name] = rule

    def copy(self):
        policy = Policy()
        policy.rules = self.rules.copy()
        policy.context = self.context.copy()
        return policy

    def derive(self, context):
        policy = self.copy()
        policy.context.update(context)
        return policy

    def _check(self, ruleName):
        rule = self.rules.get(ruleName)
        if not rule:
            raise AuthzError("No such rule %s" % ruleName)
        return rule.check(self.context)

    def check(self, ruleName):
        try:
            return self._check(ruleName)
        except AuthzError as e:
            raise AuthzError("Error while evaluating %s: %s" % (ruleName, e))


class Rule:
    def __init__(self, name, description, expression):
        self.name = name
        self.description = description
        expression = self.translateExp(expression)
        expression = self.interpolate(expression)
        self.expression = expression

    def check(self, context):
        # This is not secure - but user-defined expressions should not be used.
        # Only the contents of context may be user-provided.
        # print(self.name, context)
        return eval(self.expression, {'__builtins__': {}}, context)

    def translateExp(self, expression):
        # Grammar is already the same as Python expressions
        return expression

    def interpolate(self, expression):
        return re.sub(r'@(\w+)', r'_authz("\1")', expression)

    def __str__(self):
        return self.expression


class AuthzError(Exception):
    pass


policy = Policy()
