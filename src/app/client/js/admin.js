'use strict';

angular.module('wsaa.admin', [
    'ngResource', 'ngSanitize', 'ui.select', 'ngCookies'])

.factory('User', ['$resource', function($resource) {
    return $resource('/user/:id.json', {id: '@id'}, {
        get: { method: 'GET' },
        save: { method: 'PUT' },
        query: { method: 'GET', url: '/user.json', isArray: true,
            cache: false },
        create: { method: 'POST', url: '/user.json' },
        impersonate: { method: 'PUT', url: '/login/:id' }
    });
}])


.factory('Current', [
        'User', '$q', '$cookies', 'Notifications',
         function(User, $q, $cookies, Notifications) {
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
        function error(details) {
            var message;
            if (details.statusText)
                message = "Failed to get current user: " + details.statusText;
            else
                message = "Failed to get current user";
            Notifications.add('Current', 'error', message)
            return details;
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
        query: { method: 'GET', url: '/organisation.json', isArray: true,
            cache: false },
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
        this.saving = false;
    };

    Editor.prototype.edit = function() {
        log.debug("Creating edit object");
        this.model = angular.copy(this.getter(this.scope));
    };

    Editor.prototype.cancel = function() {
        this.model = null;
        Notifications.remove('edit');
    };

    Editor.prototype.save = function() {
        this.scope.$broadcast('show-errors-check-validity');

        var that = this;
        var success = function(model, getResponseHeaders) {
            try {
                log.debug("Success");
                that.getter.assign(that.scope, model);
                that.model = null;
                Notifications.remove('edit');
                Notifications.add('edit', 'success', "Saved", 5000);
            } finally {
                that.saving = false;
                that = null;
            }
        };
        var failure = function(details) {
            try {
                var errorText = "Could not save object: " + details.statusText;
                log.error(errorText);
                Notifications.add('edit', 'error', errorText);
            } finally {
                that.saving = false;
                that = null;
            }
        };

        if (!this.model.id) {
            log.info("Saving as new entry");
            this.model.$create(success, failure);
        } else {
            log.info("Saving over old entry");
            this.model.$save(success, failure);
        }
        this.saving = true;
    };

    Editor.prototype.destroy = function() {
        this.cancel();
        this.scope = null;
        this.getter = null;
        this.dao = null;
    };

    return function(dao, targetPath, scope) {
        log.debug('Creating editor');
        var editor = new Editor(dao, targetPath, scope);
        scope.$on('$destroy', function() {
            editor.destroy();
            editor = null;
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
                case 'user_enable':
                    if (current.user.id == user.id)
                        return false;
                    // fall-through
                case 'user_edit':
                    if (Roles.hasPermission(current.user.role, 'admin'))
                        return true;
                    if (current.user.id == user.id)
                        return true;
                    if (current.user.organisation.id != user.organisation.id)
                        return false;
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
        '$window', '$location', 'log', 'Notifications',
        function($scope, User, routeData, Editor, Organisation, userAuthz,
                 $window, $location, log, Notifications) {

    $scope.current = routeData.current;
    $scope.edit = Editor(User, 'user', $scope);
    if (routeData.user) {
        // Editing old
        $scope.user = routeData.user;
    } else {
        // Creating new
        var org;
        if ($location.search().orgId) {
            org = {
                id: $location.search().orgId,
                name: $location.search().orgName
            };
        } else {
            org = $scope.current.user.organisation;
        }
        $scope.user = new User({
            role: 'clerk',
            organisation: org
        });
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

    $scope.toggleEnabled = function() {
        $scope.user.enabled = !$scope.user.enabled;
        $scope.user.$save(
            function success() {},
            function failure(details) {
                var errorText = "Could not save object: " + details.statusText;
                log.error(errorText);
                Notifications.add('edit', 'error', errorText);
            }
        );
    };
}])


.controller('UserListCtrl', ['$scope', 'routeData', 'userAuthz', 'User',
        function($scope, routeData, userAuthz, User) {

    $scope.users = routeData.users;
    $scope.current = routeData.current;

    $scope.checkRole = userAuthz($scope.current, null);

    $scope.search = {
        term: ""
    };
    $scope.$watch('search', function(search) {
        User.query(search).$promise.then(function(users) {
            $scope.users = users;
        });
    }, true);
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
        '$scope', 'Organisation', 'routeData', 'Editor', 'orgAuthz', 'User',
        function($scope, Organisation, routeData, Editor, orgAuthz, User) {

    $scope.current = routeData.current;

    $scope.edit = Editor(Organisation, 'org', $scope);
    if (routeData.org) {
        // Editing old
        $scope.org = routeData.org;
    } else {
        // Creating new
        $scope.org = new Organisation({});
        $scope.edit.edit();
    }
    $scope.users = routeData.users;

    $scope.checkRole = orgAuthz($scope.current, $scope.org);

    $scope.search = {
        term: ""
    };
    $scope.$watch('search', function(search) {
        var params = angular.extend({org_id: $scope.org.id}, search);
        User.query(params).$promise.then(function(users) {
            $scope.users = users;
        });
    }, true);
}])


.controller('OrganisationListCtrl', [
            '$scope', 'routeData', 'orgAuthz', 'Organisation', 'Notifications',
        function($scope, routeData, orgAuthz, Organisation, Notifications) {

    $scope.current = routeData.current;
    $scope.orgs = routeData.orgs;

    $scope.checkRole = orgAuthz($scope.current, null);

    $scope.search = {
        term: ""
    };
    $scope.$watch('search', function(search) {
        Organisation.query(search).$promise.then(function(orgs) {
            $scope.orgs = orgs;
        });
    }, true);
}])

;
