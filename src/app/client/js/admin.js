'use strict';

angular.module('wsaa.admin', ['ngResource'])


.factory('User', ['$resource', function($resource) {
    return $resource('/user/:id.json', {id: '@id'}, {
        get: { method: 'GET' },
        save: { method: 'PUT' },
        query: { method: 'GET', url: '/user.json', isArray: true },
        create: { method: 'POST', url: '/user.json' }
    });
}])


.factory('Roles', ['$resource', function($resource) {
    return $resource('/roles.json', {}, {
        get: { method: 'GET', isArray: true }
    });
}])


.factory('Organisation', ['$resource', function($resource) {
    return $resource('/organisation/:id.json', {id: '@id'}, {
        get: { method: 'GET' },
        save: { method: 'PUT' },
        query: { method: 'GET', url: '/organisation.json', isArray: true },
        create: { method: 'POST', url: '/organisation.json' }
    });
}])


.factory('Editor', ['$parse', function($parse) {
    Editor = function(dao, targetPath, scope) {
        this.dao = dao;
        this.model = null;
        this.scope = scope;
        this.getter = $parse(targetPath);
        this.error = null;
        this.saving = false;
    };

    Editor.prototype.edit = function() {
        log.debug("Creating edit object");
        this.model = angular.copy(this.getter(this.scope));
    };

    Editor.prototype.cancel = function() {
        this.model = null;
        this.error = null;
    };

    Editor.prototype.save = function() {
        var new_model;
        if (!this.model.id) {
            log.info("Saving as new organisation");
            new_model = dao.create(this.model);
        } else {
            log.info("Saving over old organisation");
            new_model = dao.save(this.model);
        }
        this.saving = true;

        new_model.$promise.then(
            function success(new_model) {
                log.debug("Success");
                this.getter.assign(this.scope, new_model);
                this.model = null;
                this.saving = false;
            },
            function error(details) {
                log.error("Could not save object");
                this.error = "Could not save object";
                this.saving = false;
            }
        );
    };

    Editor.prototype.destroy = function() {
        this.scope = null;
        this.model = null;
        this.getter = null;
        this.dao = null;
    };

    return function(dao, targetPath, scope) {
        var editor = new Editor(dao, targetPath, scope);
        scope.$on('$destroy', function() {
            editor.destroy();
        });
        return editor;
    };
}])


.controller('UserCtrl', ['$scope', 'User', 'user', 'roles', 'log',
        function($scope, User, user, roles, log) {

    $scope.user = user;
    $scope.user_edit = null;

    $scope.roles = roles;
    $scope.roleDict = {};
    for (var i in roles) {
        var role = roles[i];
        $scope.roleDict[role.id] = role;
    }

    $scope.edit = function() {
        log.debug("Creating edit object");
        $scope.user_edit = angular.copy(user);
    };

    $scope.save = function() {
        var new_user;
        if (!$scope.id) {
            log.info("Saving as new organisation");
            new_user = User.create($scope.user_edit);
        } else {
            log.info("Saving over old organisation");
            new_user = User.save($scope.user_edit);
        }
        new_user.$promise.then(
            function success(new_user) {
                log.debug("Success");
                $scope.user = new_user;
                $scope.user_edit = null;
                new_user = null;
            },
            function error(details) {
                log.error("Could not save organisation");
                new_user = null;
            }
        );
    };

    $scope.$on('$destroy', function() {
        $scope = null;
    });
}])


.controller('OrganisationCtrl', ['$scope', 'Organisation', 'org', 'log',
        function($scope, Organisation, org, log) {

    $scope.org = org;
    $scope.org_edit = null;

    $scope.edit = function() {
        log.debug("Creating edit object");
        $scope.org_edit = angular.copy(org);
    };

    $scope.save = function() {
        var new_org;
        if (!$scope.id) {
            log.info("Saving as new organisation");
            new_org = Organisation.create($scope.org_edit);
        } else {
            log.info("Saving over old organisation");
            new_org = Organisation.save($scope.org_edit);
        }
        new_org.$promise.then(
            function success(new_org) {
                log.debug("Success");
                $scope.org = new_org;
                $scope.org_edit = null;
                new_org = null;
            },
            function error(details) {
                log.error("Could not save organisation");
                new_org = null;
            }
        );
    };

    $scope.$on('$destroy', function() {
        $scope = null;
    });
}])

;
