'use strict';

angular.module('wsaa.admin', [
    'ngResource', 'ngSanitize', 'ui.select', 'ngCookies'])

.factory('User', ['$resource', function($resource) {
    return $resource('/user/:id.json', {id: '@id'}, {
        get: { method: 'GET', cache: false },
        save: { method: 'PUT', cache: false },
        query: { method: 'GET', url: '/user.json', isArray: true,
            cache: false },
        create: { method: 'POST', url: '/user.json', cache: false },
        impersonate: { method: 'PUT', url: '/login/:id', cache: false }
    });
}])


.factory('Current', [
        'User', '$q', '$cookies', 'Notifications',
         function(User, $q, $cookies, Notifications) {
    var deferred = $q.defer();
    var Current = {
        user: User.get({id: 'current'}),
        superuser: $cookies.get('superuser') != null,
        $promise: null,
        $resolved: false
    };
    Current.$promise = $q.all([Current.user.$promise]).then(
        function success(values) {
            Current.$resolved = true;
            return Current;
        },
        function error(details) {
            Notifications.set('Current', 'error',
                "Failed to get current user: " + details.statusText)
            return $q.reject(details);
        }
    );
    return Current;
}])


.factory('Roles', ['$resource', function($resource) {
    var Roles = $resource('/roles.json', {}, {
        get: { method: 'GET', isArray: true, cache: false }
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
        if (!currentRole)
            return false;
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
        get: { method: 'GET', cache: false },
        save: { method: 'PUT', cache: false },
        query: { method: 'GET', url: '/organisation.json', isArray: true,
            cache: false },
        create: { method: 'POST', url: '/organisation.json', cache: false }
    });
}])


/**
 * Manages state for a modal editing session.
 */
.factory('Editor', [
        '$parse', 'log', '$filter', 'Notifications', '$q',
         function($parse, log, $filter, Notifications, $q) {

    function Editor(targetPath, scope) {
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
                that.scope.$emit('EditSaved', model);
                Notifications.set('edit', 'success', "Saved", 5000);
            } finally {
                that.saving = false;
                that = null;
            }
        };
        var failure = function(details) {
            try {
                that.scope.$emit('EditError');
                Notifications.set('edit', 'error',
                    "Could not save object: " + details.statusText);
            } finally {
                that.saving = false;
                that = null;
                return $q.reject(details);
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
        Notifications.set('edit', 'info', "Saving");
    };

    Editor.prototype.destroy = function() {
        this.cancel();
        this.scope = null;
        this.getter = null;
    };

    return function(targetPath, scope) {
        log.debug('Creating editor');
        var editor = new Editor(targetPath, scope);
        scope.$on('$destroy', function() {
            editor.destroy();
            editor = null;
        });
        return editor;
    };
}])


.factory('userAuthz', ['Roles', function(Roles) {
    return function(current, user, org) {
        return function(functionName) {
            if (!current.$resolved)
                return false;
            switch(functionName) {
                case 'user_add':
                    if (Roles.hasPermission(current.user.role, 'admin'))
                        return true;
                    if (!Roles.hasPermission(current.user.role, 'org_admin'))
                        return false;
                    return !org || org.id == current.user.organisation.id;
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
                    if (!user.id)
                        return false;
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
        '$window', '$location', 'log', 'Notifications', 'Current', '$q',
        function($scope, User, routeData, Editor, Organisation, userAuthz,
                 $window, $location, log, Notifications, Current, $q) {

    $scope.edit = Editor('user', $scope);
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
            org = Current.user.organisation;
        }
        $scope.user = new User({
            role: 'clerk',
            organisation: org
        });
        $scope.edit.edit();
    }

    $scope.$on('EditSaved', function(event, model) {
        $location.url('/user/' + model.id);
    });

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

    $scope.checkRole = userAuthz(Current, $scope.user);

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
            function success() {
                Notifications.add('edit', 'success', 'Saved', 5000);
            },
            function failure(details) {
                Notifications.set('edit', 'error',
                    "Could not save object: " + details.statusText);
                return $q.reject(details);
            }
        );
    };
}])


.controller('UserListCtrl', ['$scope', 'userAuthz', 'User', 'Current',
            'Notifications', '$q',
        function($scope, userAuthz, User, Current, Notifications, $q) {

    $scope.users = null;
    $scope.checkRole = userAuthz(Current, null, $scope.org);

    $scope.search = {
        term: "",
        org_id: $scope.org && $scope.org.id,
        enabled: true,
        page: 0,
        pageSize: 10
    };
    $scope.$watch('search', function(search) {
        User.query(search).$promise.then(
            function success(users) {
                $scope.users = users;
            },
            function failure(details) {
                console.log(details)
                Notifications.set('get', 'error',
                    "Could not get list: " + details.statusText, 10000);
                return $q.reject(details);
            }
        );
    }, true);

    $scope.cycleEnabled = function() {
        switch ($scope.search.enabled) {
            case true:
                $scope.search.enabled = null;
                break;
            case null:
                $scope.search.enabled = false;
                break;
            case false:
                $scope.search.enabled = true;
                break;
        }
    };
}])


.directive('userList', [function() {
    return {
        restrict: 'E',
        templateUrl: 'user_list.html',
        scope: {
            org: '='
        },
        controller: 'UserListCtrl'
    }
}])


.factory('orgAuthz', ['Roles', function(Roles) {
    return function(current, org) {
        return function(functionName) {
            if (!current.$resolved)
                return false;
            switch(functionName) {
                case 'org_add':
                    return Roles.hasPermission(current.user.role, 'admin');
                    break;
                case 'org_modify':
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
        '$location', 'Current',
        function($scope, Organisation, routeData, Editor, orgAuthz, User,
            $location, Current) {

    $scope.edit = Editor('org', $scope);
    if (routeData.org) {
        // Editing old
        $scope.org = routeData.org;
    } else {
        // Creating new
        $scope.org = new Organisation({});
        $scope.edit.edit();
    }

    $scope.$on('EditSaved', function(event, model) {
        $location.url('/org/' + model.id);
    });

    $scope.checkRole = orgAuthz(Current, $scope.org);
}])


.controller('OrganisationListCtrl', [
            '$scope', 'orgAuthz', 'Organisation', 'Notifications', 'Current',
            '$q',
        function($scope, orgAuthz, Organisation, Notifications, Current, $q) {

    $scope.orgs = null;
    $scope.checkRole = orgAuthz(Current, null);

    $scope.search = {
        term: "",
        page: 0,
        pageSize: 10
    };
    $scope.$watch('search', function(search) {
        Organisation.query(search).$promise.then(
            function success(orgs) {
                $scope.orgs = orgs;
            },
            function failure(details) {
                Notifications.set('get', 'error',
                    "Could not get list: " + details.statusText, 10000);
                return $q.reject(details);
            }
        );
    }, true);
}])

;
