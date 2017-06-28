import re


class Policy:
    def __init__(self, context=None, rules=None):
        self.rules = rules if rules is not None else {}
        self.context = context if context is not None else {}
        self.context['_authz'] = lambda rule_name: self._check(rule_name)

    def declare(self, decl):
        rule = Rule(decl['name'], decl['description'], decl['rule'])
        self.rules[rule.name] = rule

    def copy(self):
        return Policy(self.context.copy(), self.rules.copy())

    def derive(self, context):
        policy = self.copy()
        policy.context.update(context)
        return policy

    def _check(self, rule_name):
        rule = self.rules.get(rule_name)
        if not rule:
            raise AuthzError("No such rule %s" % rule_name)
        return rule.check(self.context)

    def check(self, rule_name):
        try:
            return self._check(rule_name)
        except AuthzError as e:
            raise AuthzError("Error while evaluating %s: %s" % (rule_name, e))


class Rule:
    def __init__(self, name, description, expression):
        self.name = name
        self.description = description
        expression = self.translate_exp(expression)
        expression = self.interpolate(expression)
        self.expression = expression

    def check(self, context):
        # This is not secure - but user-defined expressions should not be used.
        # Only the contents of context may be user-provided.
        # print(self.name, context)
        return eval(self.expression, {'__builtins__': {}}, context)

    def translate_exp(self, expression):
        # Grammar is already the same as Python expressions
        return expression

    def interpolate(self, expression):
        expression = re.sub(r'@(\w+)', r'_authz("\1")', expression)
        return expression

    def __str__(self):
        return self.expression


class AuthzError(Exception):
    pass


policy = Policy()
