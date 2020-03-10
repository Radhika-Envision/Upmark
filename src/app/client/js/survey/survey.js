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
    // hard copy survey id in production to keep export menu for old survey
    // for new survey only need one export menu 'One measure per row'   
    // **** last item "5f6b69cf-6338-4cd2-8fb8-3e6456c0ff6a" fro testing stage, remove when deploy to production
    let oldSurvey = ["19c574ad-4a02-4980-9f4a-6928ef4bc4f1",
                     "d4688eae-a732-47a2-8389-23ecdf495f04",
                     "c4ad63f1-2f10-465f-b3e6-74944602c624",
                     "eeb94743-ae00-412d-b89a-639b03677bc5",
                     "bda5e693-cd1f-4b3d-ab1b-8519f019272b",
                     "d4688eae-a732-47a2-8389-23ecdf495f04",
                     "18eab68c-1936-41e6-9de7-88d4d53a487e",
                     "eeb94743-ae00-412d-b89a-639b03677bc5",
                     "d4688eae-a732-47a2-8389-23ecdf495f04",
                     "067248b9-ee0d-4507-aad7-31159f636502",
                     "44ef39ac-b8bb-4412-b522-27b82e90a836",
                     "c8ed0f05-1a4f-49d5-b965-f3b25c74765a",
                     "19c574ad-4a02-4980-9f4a-6928ef4bc4f1",
                     "c4ad63f1-2f10-465f-b3e6-74944602c624",
                     "14a90222-7783-48c7-8127-ad10d00007c3",
                     "8ebb3782-49f7-447c-b7dc-d3c8417f12fa",
                     "4159bcbf-4416-4f94-b07a-c02c7fa4bf6a",
                     "284a5043-ffe5-4920-bb66-6a9adfa09973",
                     "57108d7a-f69e-4120-8d16-ac22f383eb0f",
                     "af7021fc-0de0-4410-975e-06ee604e225d",
                     "9ddabc3c-d259-433e-80f9-621fd685225b",
                     "7b490e0f-3e04-40e6-97ad-2ab52d19e526",
                     "d68d14cb-ad72-478c-af70-a37948e36838",
                     "5f6b69cf-6338-4cd2-8fb8-3e6456c0ff6a"];

    $scope.layout = layout;
    $scope.program = routeData.program;
    $scope.edit = Editor('survey', $scope, {programId: $scope.program.id});
    if (routeData.survey) {
        // Editing old
        $scope.survey = routeData.survey;
        $scope.children = routeData.qnodes;
        if (oldSurvey.indexOf($scope.survey.id) < 0)
            $scope.hideExportMenu=true;
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
                    hasMeasures: true,
                    indexingFrom: 1
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
            indexingFrom: 1,
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
        if (!model.structure.levels[model.structure.levels.length-1].indexingFrom)
            model.structure.levels[model.structure.levels.length-1].indexingFrom=1;    
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
