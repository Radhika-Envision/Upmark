'use strict';

angular.module('wsaa.admin', ['ngResource', 'ngSanitize', 'ui.select'])


.factory('User', ['$resource', function($resource) {
    return $resource('/user/:id.json', {id: '@id'}, {
        get: { method: 'GET' },
        save: { method: 'PUT' },
        query: { method: 'GET', url: '/user.json', isArray: true },
        create: { method: 'POST', url: '/user.json' }
    });
}])


.factory('Roles', ['$resource', function($resource) {
    var Roles = $resource('/roles.json', {}, {
        get: { method: 'GET', isArray: true }
    });

    Roles.hierarchy = {
        'admin': ['author', 'authority', 'consultant', 'org_admin', 'clerk'],
        'author': [],
        'authority': ['consultant'],
        'consultant': [],
        'org_admin': ['clerk'],
        'clerk': []
    };

    Roles.hasPermission = function(currentRole, targetRole) {
        if (targetRole == currentRole)
            return true;
        if (Roles.hierarchy[currentRole].indexOf(targetRole) >= 0)
            return true;
        return false;
    };

    Roles.checkRole = function(role, functionName) {
        if (role == "admin")
            return true;
        switch(functionName) {
            case 'user_add':
                return Roles.hasPermission(role, 'org_admin');
                break;
            case 'change_oranisation':
                return Roles.hasPermission(role, 'admin');
                break;
        }
        return false;
    };

    return Roles;
}])


.factory('Organisation', ['$resource', function($resource) {
    return $resource('/organisation/:id.json', {id: '@id'}, {
        get: { method: 'GET' },
        save: { method: 'PUT' },
        query: { method: 'GET', url: '/organisation.json', isArray: true },
        create: { method: 'POST', url: '/organisation.json' }
    });
}])


/**
 * Manages state for a modal editing session.
 */
.factory('Editor', ['$parse', 'log', '$filter', function($parse, log, $filter) {
    function Editor(dao, targetPath, scope) {
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
            log.info("Saving as new entry");
            new_model = this.dao.create(this.model);
        } else {
            log.info("Saving over old entry");
            new_model = this.dao.save(this.model);
        }
        this.saving = true;

        var that = this;
        new_model.$promise.then(
            function success(new_model) {
                log.debug("Success");
                that.getter.assign(that.scope, new_model);
                that.model = null;
                that.saving = false;
                that = null;
            },
            function error(details) {
                log.error("Could not save object");
                that.error = "Could not save object: " + details.statusText;
                that.saving = false;
                that = null;
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
        log.debug('Creating editor');
        var editor = new Editor(dao, targetPath, scope);
        scope.$on('$destroy', function() {
            editor.destroy();
        });
        return editor;
    };
}])


.directive('editorError', [function() {
    return {
        restrict: 'E',
        template: '<div ng-if="edit.error"><div class="panel panel-warning"><div class="panel-body bg-warning text-warning">{{edit.error}}</div></div></div>',
        scope: {
            edit: '='
        },
        replace: true
    };
}])


.factory('userAuthz', ['Roles', function(Roles) {
    return function(currentUser, functionName) {
        if (currentUser.role == "admin")
            return true;
        switch(functionName) {
            case 'user_add':
                return Roles.hasPermission(currentUser.role, 'org_admin');
                break;
            case 'change_org':
                return false;
                break;
        }
        return false;
    };
}])


.controller('UserCtrl', [
        '$scope', 'User', 'routeData', 'Editor', 'Organisation', 'userAuthz',
        function($scope, User, routeData, Editor, Organisation, userAuthz) {

    $scope.users = routeData.users;
    $scope.currentUser = routeData.currentUser;
    $scope.edit = Editor(User, 'user', $scope);
    if (routeData.user) {
        // Editing old
        $scope.user = routeData.user;
    } else {
        // Creating new
        $scope.user = {
            role: 'clerk',
            organisation: $scope.currentUser.organisation
        };
        $scope.edit.edit();
    }

    $scope.roles = routeData.roles;
    $scope.roleDict = {};
    for (var i in $scope.roles) {
        var role = $scope.roles[i];
        $scope.roleDict[role.id] = role;
    }

    $scope.searchOrg = function(term) {
        Organisation.query({term: term}).$promise.then(function(orgs) {
            $scope.organisations = orgs;
        });
    };

    $scope.checkRole = userAuthz;
}])


.controller('UserListCtrl', ['$scope', 'routeData', 'userAuthz',
        function($scope, routeData, userAuthz) {

    $scope.users = routeData.users;
    $scope.currentUser = routeData.currentUser;

    $scope.checkRole = userAuthz;
}])


.factory('orgAuthz', ['Roles', function(Roles) {
    return function(currentUser, org, functionName) {
        console.log(currentUser, org, functionName)
        if (currentUser.role == "admin")
            return true;
        switch(functionName) {
            case 'org_add':
                return false;
                break;
            case 'org_modify':
                if (currentUser.organisation.id != org.id)
                    return false;
                return Roles.hasPermission(currentUser.role, 'org_admin');
                break;
        }
        return false;
    };
}])


.controller('OrganisationCtrl', [
        '$scope', 'Organisation', 'routeData', 'Editor', 'orgAuthz',
        function($scope, Organisation, routeData, Editor, orgAuthz) {

    $scope.currentUser = routeData.currentUser;

    $scope.edit = Editor(Organisation, 'org', $scope);
    if (routeData.org) {
        // Editing old
        $scope.org = routeData.org;
    } else {
        // Creating new
        $scope.org = {};
        $scope.edit.edit();
    }

    $scope.checkRole = orgAuthz;
}])


.controller('OrganisationListCtrl', ['$scope', 'routeData', 'orgAuthz',
        function($scope, routeData, orgAuthz) {

    $scope.currentUser = routeData.currentUser;
    $scope.orgs = routeData.orgs;

    $scope.checkRole = orgAuthz;
}])

;
