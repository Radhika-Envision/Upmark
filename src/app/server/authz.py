# IMPORTANT: Make sure this module matches the functionality of authz.py.

import re

from munch import DefaultMunch

from undefined import undefined


class Policy:
    def __init__(self, context=None, rules=None, error_factory=None):
        self.rules = rules if rules is not None else {}
        self.context = context if context is not None else DefaultMunch(
            undefined)
        self.error_factory = error_factory if error_factory else AccessDenied

    def declare(self, decl):
        rule = Rule(
            decl['name'], decl['expression'],
            decl.get('description'), decl.get('failure'))
        self.rules[rule.name] = rule

    def copy(self):
        context = DefaultMunch(undefined, self.context)
        return Policy(context, self.rules.copy(), self.error_factory)

    def derive(self, context):
        policy = self.copy()
        policy.context.update(context)
        return policy

    def _check(self, rule_name, context):
        rule = self.rules.get(rule_name)
        if not rule:
            raise AuthzConfigError("No such rule %s" % rule_name)
        try:
            if rule.check(context):
                return True
        except AuthzConfigError:
            raise
        except Exception as e:
            raise AuthzConfigError(
                "Error while evaluating %s: %s" % (rule_name, e))
        context['_failures'].append(rule)
        return False

    def permission(self, rule_name):
        context = self.context.copy()
        context['_authz'] = lambda rule_name: self._check(rule_name, context)
        context['in'] = lambda x, xs: x in xs
        context['_failures'] = []
        success = self._check(rule_name, context)
        return Permission(rule_name, success, context['_failures'])

    def check(self, rule_name):
        return bool(self.permission(rule_name))

    def verify(self, rule_name):
        permission = self.permission(rule_name)
        if not permission:
            raise self.error_factory(str(permission))


class Permission:
    def __init__(self, rule_name, success, failures):
        self.rule_name = rule_name
        self.success = success
        self.failures = failures

    def __bool__(self):
        return self.success

    def __eq__(self, other):
        if hasattr(other, 'failures'):
            return self.failures == other.failures
        return bool(self) == other

    def __str__(self):
        if self:
            return "Granted"

        return "Denied: %s" % '; '.join(
            rule.failure for rule in reversed(self.failures)
            if rule.failure)


class Rule:
    def __init__(self, name, expression, description=None, failure=None):
        self.name = name
        self.description = description
        self.failure = failure
        self.expression = expression
        expression = self.translate_exp(expression)
        expression = self.interpolate(expression)
        self._expression = expression

    def check(self, context):
        # This is not secure - but user-defined expressions should not be used.
        # Only the contents of context may be user-provided.
        # print(self.name, context)
        return eval(self._expression, {'__builtins__': {}}, context)

    def translate_exp(self, expression):
        # Grammar is already the same as Python expressions
        return expression

    def interpolate(self, expression):
        expression = re.sub(r'@(\w+)', r'_authz("\1")', expression)
        return expression

    def __str__(self):
        return self.name


class AccessDenied(Exception):
    pass


class AuthzConfigError(Exception):
    pass


policy = Policy()
