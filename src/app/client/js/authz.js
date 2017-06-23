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
            var authz = function(policyName) {
                var policy = compiledPolicies[policyName];
                if (!policy) {
                    console.log("Unknown policy '" + policyName + "'");
                    return false;
                }
                return policy.check(authz.context);
            };
            authz.context = context;
            context.$authz = authz;
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
        expression = expression.replace(/(^|\s)not($|\s)/g, '$1!');
        expression = expression.replace(/(^|\s)and($|\s)/g, '$1&&$2');
        expression = expression.replace(/(^|\s)or($|\s)/g, '$1||$2');
        return expression;
    };
    Policy.prototype.interpolate = function(expression) {
        expression = expression.replace(/\{(\w+)\}/g, '\$authz("$1")');
        return expression;
    };
    Policy.prototype.toString = function() {
        return this.expression;
    };
})

;
