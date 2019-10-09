'use strict';

angular.module('upmark.survey.survey', [
    'ngResource', 'ngSanitize', 'ui.select', 'ui.sortable',
    'upmark.admin.settings', 'upmark.user', 'upmark.chain'])


.config(function($routeProvider, chainProvider) {
    $routeProvider
        .when('/:uv/survey/new', {
            templateUrl : 'survey.html',
            controller : 'SurveyCtrl',
            resolve: {routeData: chainProvider({
                program: ['Program', '$route', function(Program, $route) {
                    return Program.get({
                        id: $route.current.params.program
                    }).$promise;
                }]
            })}
        })
        .when('/:uv/survey/:survey/choice', {
            templateUrl : 'survey_choice.html',
            controller : 'SurveyChoiceCtrl',
            resolve: {routeData: chainProvider({
                survey: ['Survey', '$route',
                        function(Survey, $route) {
                    return Survey.get({
                        id: $route.current.params.survey,
                        programId: $route.current.params.program
                    }).$promise;
                }],
                program: ['survey', function(survey) {
                    return survey.program;
                }],
                org: ['Organisation', '$route',
                        function(Organisation, $route) {
                    if (!$route.current.params.organisation)
                        return null;
                    return Organisation.get({
                        id: $route.current.params.organisation
                    }).$promise;
                }]
            })}
        })
        .when('/:uv/survey/:survey', {
            templateUrl : 'survey.html',
            controller : 'SurveyCtrl',
            resolve: {routeData: chainProvider({
                survey: ['Survey', '$route',
                        function(Survey, $route) {
                    return Survey.get({
                        id: $route.current.params.survey,
                        programId: $route.current.params.program
                    }).$promise;
                }],
                program: ['survey', function(survey) {
                    return survey.program;
                }]
            })}
        })
    ;
})

.factory('Survey', ['$resource', function($resource) {
    return $resource('/survey/:id.json', {id: '@id'}, {
        get: { method: 'GET', cache: false },
        create: { method: 'POST' },
        save: { method: 'PUT' },
        query: { method: 'GET', isArray: true, cache: false },
        history: { method: 'GET', url: '/survey/:id/program.json',
            isArray: true, cache: false }
    });
}])


.controller('SurveyCtrl', function(
        $scope, Survey, routeData, Editor, Authz, layout,
        $location, format, QuestionNode, Structure,
        Notifications, download) {

    $scope.layout = layout;
    $scope.program = routeData.program;
    $scope.edit = Editor('survey', $scope, {programId: $scope.program.id});
    if (routeData.survey) {
        // Editing old
        $scope.survey = routeData.survey;
        $scope.children = routeData.qnodes;
    } else {
        // Creating new
        $scope.survey = new Survey({
            obType: 'survey',
            program: $scope.program,
            structure: {
                measure: {
                    title: 'Measures',
                    label: 'M'
                },
                levels: [{
                    title: 'Categories',
                    label: 'C',
                    hasMeasures: true
                }]
            }
        });
        $scope.children = null;
        $scope.edit.edit();
    }
    $scope.$watchGroup(['survey', 'survey.deleted'], function() {
        $scope.structure = Structure($scope.survey);
        $scope.editable = ($scope.program.isEditable &&
            !$scope.structure.deletedItem &&
            $scope.checkRole('program_node_edit'));
    });

    $scope.$on('EditSaved', function(event, model) {
        $location.url(format(
            '/3/survey/{}?program={}', model.id, $scope.program.id));
    });
    $scope.$on('EditDeleted', function(event, model) {
        $location.url(format(
            '/3/program/{}', $scope.program.id));
    });

    $scope.addLevel = function(model) {
        var last = model.structure.levels[model.structure.levels.length - 1];
        if (last.hasMeasures) {
            last.hasMeasures = false;
        }
        model.structure.levels.push({
            title: '',
            label: '',
            hasMeasures: true
        });
    };

    $scope.removeLevel = function(model, level) {
        if (model.structure.levels.length == 1)
            return;
        var i = model.structure.levels.indexOf(level);
        model.structure.levels.splice(i, 1);
        if (model.structure.levels.length == 1)
            model.structure.levels[0].hasMeasures = true;
    };

    $scope.download = function(export_type) {
        var fileName = 'survey-' + export_type + '.xlsx'
        var url = '/report/prog/export/' + $scope.program.id;
        url += '/survey/' + $scope.survey.id;
        url += '/' + export_type + '.xlsx';

        download(fileName, url).then(
            function success(response) {
                var message = "Export finished";
                Notifications.set('export', 'info', message, 5000);
            },
            function failure(response) {
                Notifications.set('export', 'error',
                    "Error: " + response.statusText);
            }
        );
    };

    $scope.checkRole = Authz({program: $scope.program});
    $scope.QuestionNode = QuestionNode;
    $scope.Survey = Survey;
})


.controller('SurveyChoiceCtrl', function(
        $scope, routeData, Structure, Authz, currentUser,
        Survey, layout, $location) {

    $scope.layout = layout;
    $scope.program = routeData.program;
    $scope.survey = routeData.survey;
    $scope.org = routeData.org;
    $scope.structure = Structure($scope.survey);

    if (currentUser.role == 'author')
        $location.path('/3/survey/' + $scope.survey.id);

    $scope.Survey = Survey;
    $scope.checkRole = Authz({program: $scope.program});
})
