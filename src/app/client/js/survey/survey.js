'use strict';

angular.module('upmark.survey.survey', [
  'ngResource', 'ngSanitize',
  'ui.select', 'ui.sortable',
  'upmark.admin'])


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


.controller('SurveyCtrl', [
        '$scope', 'Survey', 'routeData', 'Editor', 'Authz', 'layout',
        '$location', 'Current', 'format', 'QuestionNode', 'Structure',
        'Notifications', 'download',
        function($scope, Survey, routeData, Editor, Authz, layout,
                 $location, current, format, QuestionNode, Structure,
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
            '/2/survey/{}?program={}', model.id, $scope.program.id));
    });
    $scope.$on('EditDeleted', function(event, model) {
        $location.url(format(
            '/2/program/{}', $scope.program.id));
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
}])


.controller('SurveyChoiceCtrl', [
        '$scope', 'routeData', 'Structure', 'Authz', 'Current',
        'Survey', 'layout', '$location', 'Roles',
        function($scope, routeData, Structure, Authz, current,
                 Survey, layout, $location, Roles) {
    $scope.layout = layout;
    $scope.program = routeData.program;
    $scope.survey = routeData.survey;
    $scope.org = routeData.org;
    $scope.structure = Structure($scope.survey);

    if (current.user.role == 'author')
        $location.path('/2/survey/' + $scope.survey.id);

    $scope.Survey = Survey;
    $scope.checkRole = Authz({program: $scope.program});
}])
