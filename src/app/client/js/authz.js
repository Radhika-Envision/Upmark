'use strict';

// IMPORTANT: Make sure this module matches the functionality of authz.py.

angular.module('upmark.authz', [])


.factory('Authz', function($parse) {

    function Policy(context, rules, errorFactory) {
        this.rules = rules != null ? rules : {};
        this.context = context != null ? context : {};
        this.errorFactory = errorFactory ? errorFactory : defaultErrorFactory;
    };
    Policy.prototype.declare = function(decl) {
        var rule = new Rule(
            decl.name, decl.expression, decl.description, decl.failure);
        this.rules[rule.name] = rule;
    };
    Policy.prototype.copy = function() {
        return new Policy(
            angular.extend({}, this.context),
            angular.extend({}, this.rules)
        );
    };
    Policy.prototype.derive = function(context) {
        var policy = this.copy();
        angular.extend(policy.context, context);
        return policy;
    };
    Policy.prototype._check = function(ruleName, context) {
        var rule = this.rules[ruleName];
        if (!rule)
            throw new AuthzConfigError("Unknown rule '" + ruleName + "'");
        try {
            if (rule.check(context))
                return true;
        } catch (e) {
            if (e.name == 'AuthzConfigError')
                throw e;
            throw new AuthzConfigError(
                "Error while evaluating " + ruleName + ": " + e);
        }
        context.$failures.push(rule);
        return false;
    };
    Policy.prototype.permission = function(ruleName) {
        var context = angular.extend({}, this.context);
        var that = this;
        context.$authz = function(ruleName) {
            return that._check(ruleName, context);
        };
        context.len = function(arr) {
            return arr.length;
        };
        context.$failures = [];
        var success;
        try {
            success = this._check(ruleName, context);
        } finally {
            that = null;
        }
        return new Permission(ruleName, success, context.$failures);
    };
    Policy.prototype.check = function(ruleName) {
        var permission = this.permission(ruleName)
        return permission.valueOf();
    };
    Policy.prototype.verify = function(ruleName) {
        var permission = this.permission(ruleName)
        if (!permission.valueOf())
            throw this.error_factory(permission.toString());
    };


    function Permission(ruleName, success, failures) {
        this.ruleName = ruleName;
        this.success = success;
        this.failures = failures;
    };
    Permission.prototype.valueOf = function() {
        return this.success;
    };
    Permission.prototype.toString = function() {
        if (!!this)
            return "Success"

        return "Failure: " + this.failures.filter(function(rule) {
            return !!rule.failure;
        }).map(function(rule) {
            return rule.failure;
        }).join('; ');
    };


    function Rule(name, expression, description, failure) {
        this.name = name;
        this.description = description;
        this.expression = expression;
        this.failure = failure;
        expression = this.translateExp(expression);
        expression = this.interpolate(expression);
        // Use Angular's expression parser.
        this.getter = $parse(expression);
    };
    Rule.prototype.check = function(context) {
        return this.getter(context);
    };
    Rule.prototype.translateExp = function(expression) {
        // Convert expression syntax into something usable by the expression
        // parser.
        expression = expression.replace(/(^|\W)not($|\W)/g, '$1!');
        expression = expression.replace(/(^|\W)and($|\W)/g, '$1&&$2');
        expression = expression.replace(/(^|\W)or($|\W)/g, '$1||$2');
        expression = expression.replace(/(^|\W)True($|\W)/g, '$1true$2');
        expression = expression.replace(/(^|\W)False($|\W)/g, '$1false$2');
        return expression;
    };
    Rule.prototype.interpolate = function(expression) {
        expression = expression.replace(/@(\w+)/g, '\$authz("$1")');
        return expression;
    };
    Rule.prototype.toString = function() {
        return this.expression;
    };

    // Exception classes recipe by asselin of StackOverflow
    // https://stackoverflow.com/users/1639641/asselin
    // https://stackoverflow.com/a/27724419/320036
    function AccessDenied(message) {
        this.message = message;
        // Use V8's native method if available, otherwise fallback
        if ("captureStackTrace" in Error)
            Error.captureStackTrace(this, AccessDenied);
        else
            this.stack = (new Error()).stack;
    }
    AccessDenied.prototype = Object.create(Error.prototype);
    AccessDenied.prototype.name = "AccessDenied";
    AccessDenied.prototype.constructor = AccessDenied;
    AccessDenied.prototype.toString = function() {
        return this.message;
    };
    function defaultErrorFactory(message) {
        return new AccessDenied(message);
    };

    function AuthzConfigError(message) {
        this.message = message;
        // Use V8's native method if available, otherwise fallback
        if ("captureStackTrace" in Error)
            Error.captureStackTrace(this, AuthzConfigError);
        else
            this.stack = (new Error()).stack;
    }
    AuthzConfigError.prototype = Object.create(Error.prototype);
    AuthzConfigError.prototype.name = "AuthzConfigError";
    AuthzConfigError.prototype.constructor = AuthzConfigError;
    AuthzConfigError.prototype.toString = function() {
        return this.message;
    };

    // TODO: change this to just return the root policy (waiting on refactor
    // elsewhere).
    var policyFactory = function(context) {
        var localPolicy = policyFactory.rootPolicy.derive(context);
        return function(ruleName) {
            return localPolicy.check(ruleName);
        };
    };
    policyFactory.rootPolicy = new Policy();
    return policyFactory;
})

;
