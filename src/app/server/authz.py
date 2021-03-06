# IMPORTANT: Make sure this module matches the functionality of authz.py.

import logging
import re

from munch import DefaultMunch

from undefined import undefined


log = logging.getLogger('app.authz')


class Policy:
    def __init__(
            self, context=None, rules=None, error_factory=None, aspect=None):
        self.rules = rules if rules is not None else {}
        self.context = context if context is not None else DefaultMunch(
            undefined)
        self.error_factory = error_factory if error_factory else AccessDenied
        self.aspect = aspect

    def declare(self, decl):
        expression = decl['expression']
        if isinstance(expression, dict):
            # Rule has various aspects. Use matching aspect; deny by default.
            expression = decl['expression'].get(self.aspect, 'False')

        rule = Rule(
            decl['name'], expression,
            decl.get('description'), decl.get('failure'))
        self.rules[rule.name] = rule

    def copy(self):
        return Policy(
            DefaultMunch(undefined, self.context),
            self.rules.copy(),
            self.error_factory, self.aspect)

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
        context['len'] = lambda xs: len(xs)
        context['_failures'] = []
        success = self._check(rule_name, context)
        return Permission(rule_name, success, context, context['_failures'])

    def check(self, *rule_names, match='ANY'):
        permissions = [self.permission(rule_name) for rule_name in rule_names]
        if log.isEnabledFor(logging.DEBUG):
            for permission in permissions:
                log.debug("%s: %s", permission.rule_name, permission)
        if match == 'ANY':
            return any(permissions)
        elif match == 'ALL':
            return all(permissions)
        elif match == 'NONE':
            return not any(permissions)
        else:
            raise ValueError("Unknown match type %s" % match)

    def verify(self, rule_name):
        permission = self.permission(rule_name)
        log.debug(
            "%s: %s\n\t%s", permission.rule_name, permission,
            permission.context)
        if not permission:
            raise self.error_factory(str(permission))


class Permission:
    def __init__(self, rule_name, success, context, failures):
        self.rule_name = rule_name
        self.success = success
        self.context = context
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

    def __repr__(self):
        return "Rule(%r, %r, %r, %r)" % (
            self.name, self.expression, self.description, self.failure)


class AccessDenied(Exception):
    pass


class AuthzConfigError(Exception):
    pass


policy = Policy()
