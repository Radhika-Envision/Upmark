'use strict';

angular.module('wsaa.admin', [
    'ngResource', 'ngSanitize', 'ui.select', 'ngCookies', 'color.picker'])

.factory('User', ['$resource', 'paged', function($resource, paged) {
    return $resource('/user/:id.json', {id: '@id'}, {
        get: { method: 'GET', cache: false },
        save: { method: 'PUT', cache: false },
        query: {
            method: 'GET', isArray: true, cache: false,
            interceptor: {response: paged}
        },
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


.factory('Organisation', ['$resource', 'paged', function($resource, paged) {
    return $resource('/organisation/:id.json', {id: '@id'}, {
        get: { method: 'GET', cache: false },
        save: { method: 'PUT', cache: false },
        query: {
            method: 'GET', isArray: true, cache: false,
            interceptor: {response: paged}
        },
        create: { method: 'POST', cache: false }
    });
}])


.factory('PurchasedSurvey', ['$resource', 'paged', function($resource, paged) {
    return $resource('/organisation/:id/survey/:hid.json', {
        id: '@orgId',
        hid: '@surveyId'
    }, {
        head: { method: 'HEAD', cache: false },
        query: {
            method: 'GET', isArray: true, cache: false,
            interceptor: {response: paged}
        },
        save: { method: 'PUT', cache: false }
    });
}])


.factory('LocationSearch', ['$resource', function($resource) {
    return $resource('/geo/:term.json', {}, {
        get: { method: 'GET', cache: false },
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
                case 'user_del':
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
        'Password', 'format',
        function($scope, User, routeData, Editor, Organisation, userAuthz,
                 $window, $location, log, Notifications, Current, $q,
                 Password, format) {

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
            organisation: org,
            emailInterval: 86400,
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

    $scope.roles = routeData.roles;
    $scope.roleDict = {};
    for (var i in $scope.roles) {
        var role = $scope.roles[i];
        $scope.roleDict[role.id] = role;
    }

    $scope.searchOrg = function(term) {
        return Organisation.query({term: term}).$promise;
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
}])


.directive('userList', [function() {
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
}])


.factory('orgAuthz', ['Roles', function(Roles) {
    return function(current, org) {
        return function(functionName) {
            if (!current.$resolved)
                return false;
            switch(functionName) {
                case 'org_del':
                    if (current.user.organisation.id == org.id)
                        return false;
                    return Roles.hasPermission(current.user.role, 'admin');
                    break;
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
                case 'submission_browse':
                    if (current.user.organisation.id == org.id)
                        return true;
                    return Roles.hasPermission(current.user.role, 'consultant');
                    break;
                case 'survey_purchase':
                    return Roles.hasPermission(current.user.role, 'admin');
                    break;
            }
            return false;
        };
    };
}])


.controller('OrganisationCtrl', [
        '$scope', 'Organisation', 'org', 'Editor', 'orgAuthz', 'User',
        '$location', 'Current', 'LocationSearch',
        function($scope, Organisation, org, Editor, orgAuthz, User,
            $location, Current, LocationSearch) {

    $scope.edit = Editor('org', $scope);
    if (org) {
        // Editing old
        $scope.org = org;
    } else {
        // Creating new
        $scope.org = new Organisation({});
        $scope.org.locations = [];
        $scope.org.meta = {};
        $scope.edit.edit();
    }
    $scope.attributions = [];

    $scope.$on('EditSaved', function(event, model) {
        $location.url('/2/org/' + model.id);
    });
    $scope.$on('EditDeleted', function(event, model) {
        $location.url('/2/orgs');
    });

    $scope.$watch('org.locations', function(locations) {
        if (!locations) {
            $scope.attributions = null;
            return;
        }
        var attributions = [];
        locations.forEach(function(loc) {
            if (loc.licence && attributions.indexOf(loc.licence) < 0)
                attributions.push(loc.licence);
        });
        $scope.attributions = attributions;
    });

    $scope.deleteLocation = function(i) {
        $scope.edit.model.locations.splice(i, 1);
    };

    $scope.searchLoc = function(term) {
        return LocationSearch.query({term: term}).$promise;
    };

    $scope.ownershipTypes = [
        {name: 'government run', desc: "Government owned and run"},
        {name: 'government owned', desc: "Government owned"},
        {name: 'private', desc: "Privately owned"},
        {name: 'shareholder', desc: "Shareholder owned"},
    ];
    $scope.getDesc = function(collection, name) {
        return collection
            .filter(function(ot) {return ot.name == name})
            [0].desc;
    };
    $scope.structureTypes = [{
        name: 'internal',
        desc: "Internal department - department of a larger organisation,"
              + " e.g. local government",
    }, {
        name: 'corporation',
        desc: "Corporation - stand-alone corporation or statutory authority",
    }];
    $scope.assetTypes = [{
        name: 'water wholesale',
        desc: "Water, wholesale (catchments, storage, treament or transmission)",
    }, {
        name: 'water local',
        desc: "Water, local distribution",
    }, {
        name: 'wastewater wholesale',
        desc: "Wastewater, wholesale (trunks, treatment or disposal)",
    }, {
        name: 'wastewater local',
        desc: "Wastewater, local collection",
    }];
    $scope.regulationLevels = [{
        name: 'extensive',
        desc:
            "Extensive - economic regulation of revenues and/or prices,"
            + " and performance regulation of customer services, water"
            + " quality and/or wastewater effluent/re-use quality",
    }, {
        name: 'partial',
        desc:
            "Regulation of service performance or standards but not"
            + " economic regulation",
    }, {
        name: 'none',
        desc: "None",
    }];

    $scope.checkRole = orgAuthz(Current, $scope.org);
}])


.controller('PurchasedSurveyAddCtrl', [
        '$scope', 'Program', 'PurchasedSurvey', 'org', 'program', 'Notifications',
        'Survey', '$location',
        function($scope, Program, PurchasedSurvey, org, program, Notifications,
            Survey, $location) {

    $scope.org = org;
    $scope.program = program;

    if (!$scope.program) {
        $scope.search = {
            term: "",
            deleted: false,
            pageSize: 10
        };

        $scope.$watch('search', function(search) {
            Program.query(search).$promise.then(
                function success(programs) {
                    $scope.programs = programs;
                },
                function failure(details) {
                    Notifications.set('edit', 'error',
                        "Could not get program list: " + details.statusText);
                }
            );
        }, true);
    } else {
        Survey.query({programId: $scope.program.id}).$promise.then(
            function success(surveys) {
                $scope.surveys = surveys;
            },
            function failure(details) {
                    Notifications.set('edit', 'error',
                        "Could not get survey list: " + details.statusText);
            }
        );
    }

    $scope.addSurvey = function(survey) {
        PurchasedSurvey.save({
            programId: $scope.program.id
        }, {
            orgId: $scope.org.id,
            surveyId: survey.id
        }).$promise.then(
            function success() {
                $location.url('/2/org/' + $scope.org.id);
            },
            function failure(details) {
                Notifications.set('edit', 'error',
                    "Failed to add survey: " + details.statusText);
            }
        );
    };
}])


.controller('PurchasedSurveyCtrl',
        function($scope, PurchasedSurvey, Enqueue) {

    $scope.search = {
        id: null,
        deleted: false,
    };
    $scope.$watch('org', function(org) {
        $scope.search.id = org.id;
    });
    var update = Enqueue(function() {
        if (!$scope.search.id)
            return;
        $scope.surveys = PurchasedSurvey.query($scope.search);
    });
    $scope.$watch('search', update, true);
    $scope.$on('$destroy', function() {
        $scope = null;
    });
})


.controller('OrganisationListCtrl', [
            '$scope', 'orgAuthz', 'Organisation', 'Notifications', 'Current',
            '$q',
        function($scope, orgAuthz, Organisation, Notifications, Current, $q) {

    $scope.orgs = null;
    $scope.checkRole = orgAuthz(Current, null);

    $scope.search = {
        term: "",
        deleted: false,
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
            switch (functionName) {
                case 'adhoc_analytics':
                    return Roles.hasPermission(current.user.role, 'consultant');
                default:
                    return Roles.hasPermission(current.user.role, 'admin');
            }
        };
    };
}])


.controller('SystemConfigCtrl',
        function($scope, SystemConfig, Editor, confAuthz, Current,
            systemConfig, $q, Notifications, $window) {

    $scope.edit = Editor('systemConfig', $scope);
    $scope.systemConfig = systemConfig;
    $scope.state = {
        cacheBust: Date.now(),
        showPreview: false,
    };

    $scope.$watch('systemConfig', function(systemConfig) {
        // Small hack to get Editor utilty to use PUT instead of POST
        if (!systemConfig.id)
            systemConfig.id = 'systemConfig';
    });

    $scope.save = function() {
        var async_task_promises = [];
        $scope.$broadcast('prepareFormSubmit', async_task_promises);
        var promise = $q.all(async_task_promises).then(
            function success(async_tasks) {
                Notifications.remove('systemConfig');
                $window.location.reload();
                $scope.state.cacheBust = Date.now();
                return $scope.edit.save();
            },
            function failure(reason) {
                Notifications.set('systemConfig', 'error', reason);
                $scope.state.cacheBust = Date.now();
                return $q.reject(reason);
            }
        );
    };

    $scope.checkRole = confAuthz(Current);
})


.directive('numericalSetting', function() {
    return {
        restrict: 'E',
        scope: {
            setting: '='
        },
        require: '^form',
        templateUrl: 'setting-numerical.html',
        link: function(scope, elem, attrs, formCtrl) {
            scope.reset = function () {
                scope.setting.value = scope.setting.defaultValue;
                formCtrl.$setDirty();
            };

            scope.isFinite = isFinite;
        }
    };
})


.directive('stringSetting', function() {
    return {
        restrict: 'E',
        scope: {
            setting: '='
        },
        require: '^form',
        templateUrl: 'setting-string.html',
        link: function(scope, elem, attrs, formCtrl) {
            scope.reset = function () {
                scope.setting.value = scope.setting.defaultValue;
                formCtrl.$setDirty();
            };
        }
    };
})


.directive('booleanSetting', function() {
    return {
        restrict: 'E',
        scope: {
            setting: '='
        },
        require: '^form',
        templateUrl: 'setting-boolean.html',
        link: function(scope, elem, attrs, formCtrl) {
            scope.reset = function () {
                scope.setting.value = scope.setting.defaultValue;
                formCtrl.$setDirty();
            };
        }
    };
})


.directive('fileSetting', function($http, $cookies, $q) {
    return {
        restrict: 'E',
        scope: {
            setting: '='
        },
        templateUrl: 'setting-image.html',
        require: '^form',
        link: function(scope, elem, attrs, formCtrl) {
            var getParams = function() {
                var url = '/systemconfig/' + scope.setting.name;
                var xsrfName = $http.defaults.xsrfHeaderName;
                var headers = {};
                headers[xsrfName] = $cookies.get($http.defaults.xsrfCookieName);
                return {
                    url: url,
                    headers: headers,
                };
            };
            var dropzone;
            var deferred;
            scope.$watch('setting', function(setting) {
                var options = angular.merge({}, getParams(), {
                    maxFilesize: 50,
                    paramName: "file",
                    acceptedFiles: scope.setting.accept,
                    autoProcessQueue: false
                });
                dropzone = new Dropzone(elem.children()[0], options);

                dropzone.on('uploadprogress', function(file, progress) {
                    deferred.notify(progress);
                });

                dropzone.on("success", function(file, response) {
                    deferred.resolve();
                    setting.action = null;
                });

                dropzone.on('addedfile', function(file) {
                    if (dropzone.files.length > 1)
                        dropzone.removeFile(dropzone.files[0]);
                    setting.value = "file.name";
                    setting.action = 'upload';
                    formCtrl.$setDirty();
                    scope.$apply();
                });

                dropzone.on("error", function(file, details, request) {
                    if (request)
                        deferred.reject("Upload failed: " + request.statusText);
                    else
                        deferred.reject("Upload failed: " + details);
                });
            });

            scope.reset = function () {
                dropzone.removeAllFiles();
                scope.setting.action = 'reset';
                formCtrl.$setDirty();
            };

            scope.$on('prepareFormSubmit', function(event, promises) {
                if (scope.setting.action == 'reset') {
                    var options = angular.merge({}, getParams(), {
                        method: 'DELETE',
                    });
                    promises.push($http(options));
                    return;
                }

                if (!dropzone.files.length)
                    return;

                deferred = $q.defer();
                promises.push(deferred.promise);
                dropzone.processQueue();
            });
            scope.$on('$destroy', function() {
                scope = null;
                formCtrl = null;
                dropzone = null;
            });
        }
    };
})


.directive('colourSetting', function() {
    return {
        restrict: 'E',
        scope: {
            setting: '='
        },
        require: '^form',
        templateUrl: 'setting-colour.html',
        link: function(scope, elem, attrs, formCtrl) {
            scope.options = {
                format: 'hex8',
                swatchBootstrap: true,
                case: 'lower',
            };
            scope.reset = function () {
                scope.setting.value = scope.setting.defaultValue;
                formCtrl.$setDirty();
            };
            elem.find('.color-picker-input-wrapper').append(
                elem.find('.input-group-btn'));
        }
    };
})


;
