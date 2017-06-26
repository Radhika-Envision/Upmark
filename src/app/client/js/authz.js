'use strict';

angular.module('upmark.authz', [])


.provider('Authz', function AuthzProvider() {
    this.policies = {};

    this.addAll = function(policies) {
        angular.extend(this.policies, policies);
    };

    this.$get = function($parse) {
        var compiledPolicies = {};
        angular.forEach(this.policies, function(definition, name) {
            compiledPolicies[name] = new Policy($parse, name, definition);
        });

         var Authz = function(context) {
            context = angular.extend({}, Authz.baseContext, context);
            function _authz(policyName) {
                var policy = compiledPolicies[policyName];
                if (!policy) {
                    throw new AuthzError("Unknown policy '" + policyName + "'");
                }
                return policy.check(authz.context);
            };
            function authz(policyName) {
                try {
                    return _authz(policyName);
                } catch (e) {
                    throw new AuthzError(
                        "Error while evaluating " + policyName + ": " + e);
                }
            };
            authz.context = context;
            context.$authz = _authz;
            return authz;
        };
        Authz.baseContext = {};
        return Authz;
    };

    function Policy($parse, name, expression) {
        this.name = name;
        this.expression = expression;
        expression = this.translatePyExp(expression);
        expression = this.interpolate(expression);
        this.getter = $parse(expression);
    };
    Policy.prototype.check = function(context) {
        return this.getter(context);
    };
    Policy.prototype.translatePyExp = function(expression) {
        expression = expression.replace(/(^|\W)not($|\W)/g, '$1!');
        expression = expression.replace(/(^|\W)and($|\W)/g, '$1&&$2');
        expression = expression.replace(/(^|\W)or($|\W)/g, '$1||$2');
        return expression;
    };
    Policy.prototype.interpolate = function(expression) {
        expression = expression.replace(/\{(\w+)\}/g, '\$authz("$1")');
        return expression;
    };
    Policy.prototype.toString = function() {
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
})

;
