'use strict'

angular.module('upmark.organisation', [
    'ngResource', 'upmark.admin.settings', 'upmark.authz', 'upmark.user',
    'vpac.utils.requests', 'vpac.widgets.editor'])


.config(function($routeProvider) {
    $routeProvider
        .when('/:uv/orgs', {
            templateUrl : 'organisation_list.html',
            controller : 'OrganisationListCtrl'
        })
        .when('/:uv/org/new', {
            templateUrl : 'organisation.html',
            controller : 'OrganisationCtrl',
            resolve: {
                org: function() {
                    return null;
                }
            }
        })
        .when('/:uv/org/:id', {
            templateUrl : 'organisation.html',
            controller : 'OrganisationCtrl',
            resolve: {
                org: ['Organisation', '$route',
                        function(Organisation, $route) {
                    return Organisation.get({
                        id: $route.current.params.id
                    }).$promise;
                }]
            }
        })
        .when('/:uv/org/:id/survey/add', {
            templateUrl : 'purchased_survey.html',
            controller : 'PurchasedSurveyAddCtrl',
            resolve: {
                org: ['Organisation', '$route',
                        function(Organisation, $route) {
                    return Organisation.get($route.current.params).$promise;
                }],
                program: ['Program', '$route',
                        function(Program, $route) {
                    if (!$route.current.params.program)
                        return null;
                    return Program.get({
                        id: $route.current.params.program
                    }).$promise;
                }],
                surveys: ['Survey', '$route',
                        function(Survey, $route) {
                    if (!$route.current.params.program)
                        return null;
                    return Survey.query({
                        programId: $route.current.params.program
                    }).$promise;
                }]
            }
        })
    ;
})


.service('OrgMetaOptions', function() {
    this.ownershipTypes = [
        {name: 'government run', desc: "Government owned and run"},
        {name: 'government owned', desc: "Government owned"},
        {name: 'private', desc: "Privately owned"},
        {name: 'shareholder', desc: "Shareholder owned"},
    ];
    this.sizeTypes = [{
        name: 'small',
        desc: 'Small'
    }, {
        name: 'medium',
        desc: 'Medium'
    }, {
        name: 'large',
        desc: 'Large'
    }];
    this.structureTypes = [{
        name: 'internal',
        desc: "Internal department - department of a larger organisation,"
              + " e.g. local government",
    }, {
        name: 'corporation',
        desc: "Corporation - stand-alone corporation or statutory authority",
    }];
    this.assetTypes = [{
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
    }, {
        name: 'stormwater',
        desc: "Stormwater",
    }, {
        name: 'highway bridge',
        desc: "Highway Bridge",
    }, {
        name: 'roads',
        desc: "Roads",
    }, {
        name: 'rail',
        desc: "Rail",
    }, {
        name: 'ports',
        desc: "Ports",
    }, {
        name: 'airports',
        desc: "Airports",
    }];
    this.regulationLevels = [{
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
})


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
        id: '@organisationId',
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


.controller('OrganisationCtrl',
        function($scope, Organisation, OrgMetaOptions, org, Editor, Authz, User,
            $location, LocationSearch, SurveyGroup, currentUser) {

    $scope.edit = Editor('org', $scope);
    $scope.orgMetaOptions = OrgMetaOptions;
    if (org) {
        // Editing old
        $scope.org = org;
    } else {
        // Creating new
        $scope.org = new Organisation({
            locations: [],
            meta: {},
            surveygroups: angular.copy(currentUser.surveygroups),
        });
        $scope.edit.edit();
    }
    $scope.attributions = [];

    $scope.$on('EditSaved', function(event, model) {
        $location.url('/3/org/' + model.id);
    });
    $scope.$on('EditDeleted', function(event, model) {
        $location.url('/3/orgs');
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

    $scope.getDesc = function(collection, name) {
        return collection
            .filter(function(ot) {return ot.name == name})
            [0].desc;
    };

    $scope.deleteSurveygroup = function(i) {
        $scope.edit.model.surveygroups.splice(i, 1);
    };

    $scope.searchSurveygroup = function(term) {
        return SurveyGroup.query({term: term}).$promise;
    };

    $scope.checkRole = Authz({org: $scope.org});
})


.controller('OrganisationListCtrl',
        function($scope, Authz, Organisation, Notifications, $q) {

    $scope.orgs = null;
    $scope.checkRole = Authz({});

    $scope.search = {
        term: "",
        surveyGroupId: $scope.sg && $scope.sg.id,
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
})


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
        Survey.query({
            programId: $scope.program.id,
            deleted: false,
            organisationId: $scope.org.id,
        }).$promise.then(
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
            organisationId: $scope.org.id,
            surveyId: survey.id
        }).$promise.then(
            function success() {
                $location.url('/3/org/' + $scope.org.id);
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
    }, 0, $scope);
    $scope.$watch('search', update, true);
    $scope.$on('$destroy', function() {
        $scope = null;
    });
})


.directive('organisationList', function() {
    return {
        restrict: 'E',
        templateUrl: 'organisation_list.html',
        scope: {
            sg: '='
        },
        controller: 'OrganisationListCtrl'
    }
})


;
