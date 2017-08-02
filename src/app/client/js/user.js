'use strict'

angular.module('upmark.user', [
    'ngResource', 'upmark.notifications', 'vpac.utils.requests',
    'upmark.chain', 'upmark.surveygroup'])


.config(function($routeProvider, chainProvider) {
    $routeProvider
        .when('/:uv/users', {
            templateUrl : 'user_list.html',
            controller : 'UserListCtrl'
        })
        .when('/:uv/user/new', {
            templateUrl : 'user.html',
            controller : 'UserCtrl',
            resolve: {routeData: chainProvider({
                org: ['Organisation', '$location', 'currentUser', function(
                        Organisation, $location, currentUser) {
                    var orgId = $location.search().organisationId ||
                        currentUser.organisation.id;
                    return Organisation.get({id: orgId}).$promise;
                }],
            })},
        })
        .when('/:uv/user/:id', {
            templateUrl : 'user.html',
            controller : 'UserCtrl',
            resolve: {routeData: chainProvider({
                user: ['User', '$route', function(User, $route) {
                    return User.get($route.current.params).$promise;
                }]
            })}
        })
    ;
})


.factory('User', ['$resource', 'paged', function($resource, paged) {
    return $resource('/user/:id.json', {id: '@id'}, {
        get: { method: 'GET', cache: false },
        save: { method: 'PUT', cache: false },
        query: {
            method: 'GET', isArray: true, cache: false,
            interceptor: {response: paged}
        },
        create: { method: 'POST', cache: false },
        impersonate: { method: 'PUT', url: '/impersonate/:id', cache: false }
    });
}])


.factory('Password', ['$resource', function($resource) {
    return $resource('/password.json', {}, {
        test: { method: 'POST', cache: true }
    });
}])


.factory('roles', function(authz_rules) {
    var roles = authz_rules.filter(function(rule) {
        return rule.tags && rule.tags.indexOf('role') >= 0;
    }).map(function(rule) {
        return {
            id: rule.name,
            name: rule.human_name,
            description: rule.description,
        };
    });
    roles.$find = function(id) {
        return roles.filter(
            function(role) {
                return role.id == id;
            }
        )[0];
    };
    return roles;
})


.factory('checkLogin', ['$q', 'User', '$cookies', '$http',
         function($q, User, $cookies, $http) {
    return function checkLogin() {
        var user = $cookies.get('user');
        var xsrf = $cookies.get($http.defaults.xsrfCookieName);
        if (!user || !xsrf)
            return $q.reject("Session cookies are not defined");

        return User.get({id: 'current'}).$promise;
    };
}])


.controller('UserCtrl', function(
        $scope, User, routeData, Editor, Organisation, Authz,
        $window, $location, Notifications, currentUser, $q,
        Password, format, roles, SurveyGroup) {

    $scope.edit = Editor('user', $scope);
    if (routeData.user) {
        // Editing old
        $scope.user = routeData.user;
    } else {
        // Creating new
        var ownSurveygroupIds = currentUser.surveygroups.map(function(surveygroup) {
            return surveygroup.id;
        });
        $scope.user = new User({
            role: 'clerk',
            organisation: routeData.org,
            emailInterval: 86400,
            surveygroups: routeData.org.surveygroups.filter(function(surveygroup) {
                return ownSurveygroupIds.indexOf(surveygroup.id) >= 0;
            }),
        });
        $scope.edit.edit();
    }

    $scope.$on('EditSaved', function(event, model) {
        $location.url('/2/user/' + model.id);
    });
    $scope.$on('EditDeleted', function(event, model) {
        $location.url(format(
            '/2/org/{}', model.organisation.id));
    });

    $scope.roles = roles;
    $scope.roleDict = {};
    for (var i in $scope.roles) {
        var role = $scope.roles[i];
        $scope.roleDict[role.id] = role;
    }

    $scope.searchOrg = function(term) {
        return Organisation.query({term: term}).$promise;
    };

    $scope.checkRole = Authz({user: $scope.user});

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

    $scope.deleteSurveygroup = function(i) {
        $scope.edit.model.surveygroups.splice(i, 1);
    };

    $scope.searchSurveygroup = function(term) {
        return SurveyGroup.query({term: term}).$promise;
    };
})


.controller('UserListCtrl', function($scope, Authz, User, Notifications, $q) {

    $scope.users = null;
    $scope.checkRole = Authz({org: $scope.org});

    $scope.search = {
        term: "",
        organisationId: $scope.org && $scope.org.id,
        deleted: $scope.org && $scope.org.deleted ? null : false,
        page: 0,
        pageSize: 10
    };
    $scope.$watch('search', function(search) {
        User.query(search).$promise.then(
            function success(users) {
                $scope.users = users;
            },
            function failure(details) {
                Notifications.set('get', 'error',
                    "Could not get list: " + details.statusText);
                return $q.reject(details);
            }
        );
    }, true);
})


.directive('userList', function() {
    return {
        restrict: 'E',
        templateUrl: 'user_list.html',
        scope: {
            org: '='
        },
        controller: 'UserListCtrl',
        link: function(scope, elem, attrs) {
            scope.hideOrg = attrs.hideOrg !== undefined;
        }
    }
})


;
