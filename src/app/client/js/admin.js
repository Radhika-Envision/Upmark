'use strict';

angular.module('wsaa.admin', [
    'ngResource', 'ngSanitize', 'ui.select', 'ngCookies'])

.factory('User', ['$resource', function($resource) {
    return $resource('/user/:id.json', {id: '@id'}, {
        get: { method: 'GET', cache: false },
        save: { method: 'PUT', cache: false },
        query: { method: 'GET', isArray: true, cache: false },
        create: { method: 'POST', cache: false },
        impersonate: { method: 'PUT', url: '/login/:id', cache: false }
    });
}])


.factory('Password', ['$resource', function($resource) {
    return $resource('/password.json', {}, {
        test: { method: 'POST', cache: true }
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
        query: { method: 'GET', isArray: true, cache: false },
        create: { method: 'POST', cache: false }
    });
}])


.factory('SystemConfig', ['$resource', function($resource) {
    return $resource('/systemconfig.json', {}, {
        get: { method: 'GET', cache: false },
        save: { method: 'PUT', cache: false },
    });
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
        'Password',
        function($scope, User, routeData, Editor, Organisation, userAuthz,
                 $window, $location, log, Notifications, Current, $q,
                 Password) {

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
                $window.location.reload();
            },
            function error(details) {
                Notifications.set('user', 'error',
                    "Could not impersonate: " + details.statusText);
            }
        );
    };

    $scope.toggleEnabled = function() {
        $scope.user.enabled = !$scope.user.enabled;
        $scope.user.$save(
            function success() {
                Notifications.set('edit', 'success', 'Saved', 5000);
            },
            function failure(details) {
                Notifications.set('edit', 'error',
                    "Could not save object: " + details.statusText);
                return $q.reject(details);
            }
        );
    };

    $scope.$watch('edit.model.password', function(password) {
        if (!password) {
            $scope.passwordCheck = null;
            return;
        }
        Password.test({password: password}).$promise.then(
            function success(body) {
                $scope.passwordCheck = body;
                Notifications.remove('user');
            },
            function failure(details) {
                $scope.passwordCheck = null;
                Notifications.set('user', 'warning',
                    "Could not check password: " + details.statusText);
            }
        );
    });
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
                    if (Roles.hasPermission(current.user.role, 'admin'))
                        return true;
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
        '$scope', 'Organisation', 'org', 'Editor', 'orgAuthz', 'User',
        '$location', 'Current',
        function($scope, Organisation, org, Editor, orgAuthz, User,
            $location, Current) {

    $scope.edit = Editor('org', $scope);
    if (org) {
        // Editing old
        $scope.org = org;
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


.factory('confAuthz', ['Roles', function(Roles) {
    return function(current) {
        return function(functionName) {
            return Roles.hasPermission(current.user.role, 'admin');
        };
    };
}])


.controller('SystemConfigCtrl', [
        '$scope', 'SystemConfig', 'Editor', 'confAuthz', 'Current',
        'systemConfig',
        function($scope, SystemConfig, Editor, confAuthz, Current,
            systemConfig) {

    $scope.edit = Editor('systemConfig', $scope);
    $scope.systemConfig = systemConfig;

    $scope.checkRole = confAuthz(Current);
}])

;
