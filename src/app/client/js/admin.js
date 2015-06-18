'use strict';

angular.module('wsaa.admin', [
    'ngResource', 'ngSanitize', 'ui.select', 'ngCookies'])


.factory('User', ['$resource', function($resource) {
    return $resource('/user/:id.json', {id: '@id'}, {
        get: { method: 'GET' },
        save: { method: 'PUT' },
        query: { method: 'GET', url: '/user.json', isArray: true },
        create: { method: 'POST', url: '/user.json' },
        impersonate: { method: 'PUT', url: '/login/:id' }
    });
}])


.factory('Current', ['User', '$q', '$cookies', function(User, $q, $cookies) {
    var deferred = $q.defer();
    var Current = {
        user: User.get({id: 'current'}),
        superuser: $cookies.get('superuser') != null,
        $promise: null
    };
    Current.$promise = $q.all([Current.user.$promise]).then(
        function success(values) {
            return Current;
        },
        function error(reason) {
            return reason;
        }
    );
    return Current;
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
.factory('Editor', [
        '$parse', 'log', '$filter', 'Notifications',
         function($parse, log, $filter, Notifications) {
    function Editor(dao, targetPath, scope) {
        this.dao = dao;
        this.model = null;
        this.scope = scope;
        this.getter = $parse(targetPath);
        this.message = null;
        this.saving = false;
    };

    Editor.prototype.edit = function() {
        log.debug("Creating edit object");
        this.model = angular.copy(this.getter(this.scope));
    };

    Editor.prototype.cancel = function() {
        this.model = null;
        Notifications.remove(this.message);
        this.message = null;
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
        Notifications.remove(this.message);

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
                var errorText = "Could not save object: " + details.statusText;
                log.error(errorText);
                that.message = Notifications.add('error', errorText);
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


.factory('userAuthz', ['Roles', function(Roles) {
    return function(current, user) {
        return function(functionName) {
            switch(functionName) {
                case 'user_add':
                    return Roles.hasPermission(current.user.role, 'org_admin');
                    break;
                case 'user_edit':
                    if (current.user.id == user.id)
                        return true;
                    return Roles.hasPermission(current.user.role, 'org_admin');
                    break;
                case 'user_impersonate':
                    if (current.user.id == user.id)
                        return false;
                    return current.superuser;
                    break;
                case 'user_change_org':
                    return Roles.hasPermission(current.user.role, 'admin');
                    break;
            }
            return false;
        };
    };
}])


.controller('UserCtrl', [
        '$scope', 'User', 'routeData', 'Editor', 'Organisation', 'userAuthz',
        '$window',
        function($scope, User, routeData, Editor, Organisation, userAuthz,
                 $window) {

    $scope.users = routeData.users;
    $scope.current = routeData.current;
    $scope.edit = Editor(User, 'user', $scope);
    if (routeData.user) {
        // Editing old
        $scope.user = routeData.user;
    } else {
        // Creating new
        $scope.user = {
            role: 'clerk',
            organisation: $scope.current.user.organisation
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

    $scope.checkRole = userAuthz($scope.current, $scope.user);

    $scope.impersonate = function() {
        User.impersonate({id: $scope.user.id}).$promise.then(
            function success() {
                console.log('reloading');
                $window.location.reload();
            },
            function error(reason) {
            }
        );
    };
}])


.controller('UserListCtrl', ['$scope', 'routeData', 'userAuthz',
        function($scope, routeData, userAuthz) {

    $scope.users = routeData.users;
    $scope.current = routeData.current;

    $scope.checkRole = userAuthz($scope.current, null);
}])


.factory('orgAuthz', ['Roles', function(Roles) {
    return function(current, org) {
        return function(functionName) {
            if (current.user.role == "admin")
                return true;
            switch(functionName) {
                case 'org_add':
                    return false;
                    break;
                case 'org_modify':
                    if (current.user.organisation.id != org.id)
                        return false;
                    return Roles.hasPermission(current.user.role, 'org_admin');
                    break;
                case 'user_add':
                    if (current.user.organisation.id != org.id)
                        return false;
                    return Roles.hasPermission(current.user.role, 'org_admin');
                    break;
            }
            return false;
        };
    };
}])


.controller('OrganisationCtrl', [
        '$scope', 'Organisation', 'routeData', 'Editor', 'orgAuthz',
        function($scope, Organisation, routeData, Editor, orgAuthz) {

    $scope.current = routeData.current;

    $scope.edit = Editor(Organisation, 'org', $scope);
    if (routeData.org) {
        // Editing old
        $scope.org = routeData.org;
    } else {
        // Creating new
        $scope.org = {};
        $scope.edit.edit();
    }
    $scope.users = routeData.users;

    $scope.checkRole = orgAuthz($scope.current, $scope.org);
}])


.controller('OrganisationListCtrl', ['$scope', 'routeData', 'orgAuthz',
        function($scope, routeData, orgAuthz) {

    $scope.current = routeData.current;
    $scope.orgs = routeData.orgs;

    $scope.checkRole = orgAuthz($scope.current, null);
}])

;
