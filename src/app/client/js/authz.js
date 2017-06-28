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
        var rule = new Rule(decl.name, decl.description, decl.rule);
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
            throw new AuthzError("Unknown rule '" + ruleName + "'");
        if (rule.check(context))
            return true;
        context.$failures.push(rule);
        return false;
    };
    Policy.prototype.permission = function(ruleName) {
        var context = angular.extend({}, this.context);
        var that = this;
        context.$authz = function(ruleName) {
            return that._check(ruleName, context);
        };
        context.$failures = [];
        try {
            this._check(ruleName, context);
        } catch (e) {
            throw new AuthzError(
                "Error while evaluating " + ruleName + ": " + e);
        } finally {
            that = null;
        }
        return new Permission(context.$failures);
    };
    Policy.prototype.check = function(ruleName) {
        return this.permission(ruleName).valueOf();
    };
    Policy.prototype.verify = function(ruleName) {
        permission = this.permission(rule_name)
        if (!permission.valueOf())
            throw this.error_factory(permission.toString());
    };


    function Permission(failures) {
        this.failures = failures;
    };
    Permission.prototype.valueOf = function() {
        return !this.failures || this.failures.length == 0;
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


    function Rule(name, description, expression) {
        this.name = name;
        this.description = description;
        this.expression = expression;
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
    function AuthzError(message) {
        this.message = message;
        // Use V8's native method if available, otherwise fallback
        if ("captureStackTrace" in Error)
            Error.captureStackTrace(this, AuthzError);
        else
            this.stack = (new Error()).stack;
    }
    AuthzError.prototype = Object.create(Error.prototype);
    AuthzError.prototype.name = "AuthzError";
    AuthzError.prototype.constructor = AuthzError;
    AuthzError.prototype.toString = function() {
        return this.message;
    };
    function defaultErrorFactory(message) {
        return new AuthzError(message);
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
