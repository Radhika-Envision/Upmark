'use strict';

angular.module('wsaa.surveyQuestions', [
    'ngResource', 'ngSanitize', 'ui.select', 'ui.tree', 'ui.sortable',
    'wsaa.admin'])


.factory('Survey', ['$resource', function($resource) {
    return $resource('/survey/:id.json', {id: '@id'}, {
        get: { method: 'GET', cache: false },
        create: { method: 'POST' },
        save: { method: 'PUT' },
        query: { method: 'GET', isArray: true, cache: false }
    });
}])


.factory('Hierarchy', ['$resource', function($resource) {
    return $resource('/hierarchy/:id.json', {id: '@id'}, {
        get: { method: 'GET', cache: false },
        create: { method: 'POST' },
        save: { method: 'PUT' },
        query: { method: 'GET', isArray: true, cache: false }
    });
}])


.factory('QuestionNode', ['$resource', function($resource) {
    return $resource('/qnode/:id.json', {id: '@id'}, {
        get: { method: 'GET', cache: false },
        create: { method: 'POST' },
        save: { method: 'PUT' },
        query: { method: 'GET', isArray: true, cache: false },
        reorder: { method: 'PUT', isArray: true }
    });
}])


.factory('Measure', ['$resource', function($resource) {
    return $resource('/measure/:id.json', {id: '@id'}, {
        get: { method: 'GET', cache: false },
        create: { method: 'POST' },
        save: { method: 'PUT' },
        query: { method: 'GET', isArray: true, cache: false },
        reorder: { method: 'PUT', isArray: true }
    });
}])


.factory('questionAuthz', ['Roles', function(Roles) {
    return function(current, survey) {
        return function(functionName) {
            return Roles.hasPermission(current.user.role, 'author');
        };
    };
}])


.controller('SurveyCtrl', [
        '$scope', 'Survey', 'routeData', 'Editor', 'questionAuthz',
        '$location', 'Notifications', 'Current', 'Hierarchy', 'layout',
        function($scope, Survey, routeData, Editor, authz,
                 $location, Notifications, current, Hierarchy, layout) {

    $scope.layout = layout;
    $scope.edit = Editor('survey', $scope);
    if (routeData.survey) {
        // Viewing old
        $scope.survey = routeData.survey;
        $scope.hierarchies = routeData.hierarchies;
    } else {
        // Creating new
        $scope.survey = new Survey({});
        $scope.hierarchies = null;
        $scope.edit.edit();
    }

    $scope.$on('EditSaved', function(event, model) {
        $location.url('/survey/' + model.id);
    });
    $scope.$on('EditDeleted', function(event, model) {
        $location.url('/surveys');
    });

    $scope.checkRole = authz(current, $scope.survey);
}])


.controller('SurveyListCtrl', ['$scope', 'questionAuthz', 'Survey', 'Current',
        'layout',
        function($scope, authz, Survey, current, layout) {

    $scope.layout = layout;
    $scope.checkRole = authz(current, null);
    $scope.currentSurvey = Survey.get({id: 'current'});

    $scope.search = {
        term: "",
        page: 0,
        pageSize: 10
    };
    $scope.$watch('search', function(search) {
        Survey.query(search).$promise.then(function(surveys) {
            $scope.surveys = surveys;
        });
    }, true);
}])


.directive('questionHeader', [function() {
    return {
        restrict: 'E',
        scope: {
            entity: '=',
            type: '@'
        },
        replace: true,
        templateUrl: 'question_header.html',
        controller: ['$scope', 'layout', function($scope, layout) {
            $scope.layout = layout;

            $scope.$watch('entity', function(entity) {
                var stack = [];
                while (entity) {
                    stack.push(entity);
                    if (entity.parent)
                        entity = entity.parent;
                    else if (entity.hierarchy)
                        entity = entity.hierarchy;
                    else if (entity.survey)
                        entity = entity.survey;
                    else
                        entity = null;
                }
                stack.reverse();

                var hstack = []
                // Survey
                if (stack.length > 0) {
                    hstack.push({
                        type: 'survey',
                        label: 'S',
                        entity: stack[0]
                    });
                }
                // Hierarchy
                if (stack.length > 1) {
                    hstack.push({
                        type: 'question set',
                        label: 'Qs',
                        entity: stack[1]
                    });
                }
                // Qnodes and measures
                for (var i = 2; i < stack.length; i++) {
                    hstack.push({
                        type: 'qnode',
                        label: stack[1].levels[i - 2].label,
                        entity: stack[i]
                    });
                }
                if (hstack.length > 2) {
                    // Last node might be a qnode or a measure; for that node,
                    // take the type specified by the caller.
                    hstack[hstack.length - 1].type = $scope.type;
                }
                $scope.hstack = hstack;
            });
        }]
    }
}])


.controller('HierarchyCtrl', [
        '$scope', 'Hierarchy', 'routeData', 'Editor', 'questionAuthz', 'layout',
        '$location', 'Current', 'format', 'QuestionNode',
        function($scope, Hierarchy, routeData, Editor, authz, layout,
                 $location, current, format, QuestionNode) {

    $scope.layout = layout;
    $scope.survey = routeData.survey;
    $scope.edit = Editor('hierarchy', $scope, {surveyId: $scope.survey.id});
    if (routeData.hierarchy) {
        // Editing old
        $scope.hierarchy = routeData.hierarchy;
        $scope.qnodes = routeData.qnodes;
    } else {
        // Creating new
        $scope.hierarchy = new Hierarchy({
            survey: $scope.survey,
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
        $scope.qnodes = null;
        $scope.edit.edit();
    }

    $scope.$on('EditSaved', function(event, model) {
        $location.url(format(
            '/hierarchy/{}?survey={}', model.id, $scope.survey.id));
    });
    $scope.$on('EditDeleted', function(event, model) {
        $location.url(format(
            '/survey/{}', $scope.survey.id));
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

    $scope.checkRole = authz(current, $scope.survey);
    $scope.QuestionNode = QuestionNode;
}])


.controller('ProcessCtrl', [
        '$scope', 'Process', 'routeData', 'Editor', 'questionAuthz',
        '$location', 'Notifications', 'Current', 'Survey', 'format',
        'SubProcess', 'layout',
        function($scope, Process, routeData, Editor, authz,
                 $location, Notifications, current, Survey, format,
                 SubProcess, layout) {

    $scope.layout = layout;
    $scope.survey = routeData.survey;
    $scope.func = routeData.func;
    $scope.edit = Editor('process', $scope, {
        functionId: $scope.func.id,
        surveyId: $scope.survey.id
    });
    if (routeData.process) {
        // Editing old
        $scope.process = routeData.process;
        $scope.subprocs = routeData.subprocs;
    } else {
        // Creating new
        $scope.process = new Process({
            'function': $scope.func
        });
        $scope.subprocs = null;
        $scope.edit.edit();
    }

    $scope.$on('EditSaved', function(event, model) {
        $location.url(format(
            '/process/{}?survey={}', model.id, $scope.survey.id));
    });
    $scope.$on('EditDeleted', function(event, model) {
        $location.url(format(
            '/function/{}?survey={}', $scope.func.id, $scope.survey.id));
    });

    $scope.checkRole = authz(current, $scope.survey);
    $scope.SubProcess = SubProcess;
}])


.controller('SubProcessCtrl', [
        '$scope', 'SubProcess', 'routeData', 'Editor', 'questionAuthz',
        '$location', 'Notifications', 'Current', 'Survey', 'format', 'Measure',
        'layout',
        function($scope, SubProcess, routeData, Editor, authz,
                 $location, Notifications, current, Survey, format, Measure,
                 layout) {

    $scope.layout = layout;
    $scope.survey = routeData.survey;
    $scope.process = routeData.process;
    $scope.edit = Editor('subprocess', $scope, {
        processId: $scope.process.id,
        surveyId: $scope.survey.id
    });
    if (routeData.subprocess) {
        // Editing old
        $scope.subprocess = routeData.subprocess;
        $scope.measures = routeData.measures;
    } else {
        // Creating new
        $scope.subprocess = new SubProcess({
            process: $scope.process
        });
        $scope.measures = null;
        $scope.edit.edit();
    }

    $scope.$on('EditSaved', function(event, model) {
        $location.url(format(
            '/subprocess/{}?survey={}', model.id, $scope.survey.id));
    });
    $scope.$on('EditDeleted', function(event, model) {
        $location.url(format(
            '/process/{}?survey={}', $scope.process.id, $scope.survey.id));
    });

    $scope.checkRole = authz(current, $scope.survey);
    $scope.Measure = Measure;
}])


.controller('MeasureCtrl', [
        '$scope', 'Measure', 'routeData', 'Editor', 'questionAuthz',
        '$location', 'Notifications', 'Current', 'Survey', 'format', 'layout',
        function($scope, Measure, routeData, Editor, authz,
                 $location, Notifications, current, Survey, format, layout) {

    $scope.layout = layout;
    $scope.survey = routeData.survey;
    $scope.subprocess = routeData.subprocess;
    $scope.edit = Editor('measure', $scope, {
        subprocessId: $scope.subprocess.id,
        surveyId: $scope.survey.id
    });
    if (routeData.measure) {
        // Editing old
        $scope.measure = routeData.measure;
    } else {
        // Creating new
        $scope.measure = new Measure({
            subprocess: $scope.subprocess,
            weight: 100,
            responseType: 'standard_1'
        });
        $scope.edit.edit();
    }

    $scope.responseTypes = [
        {
            id: 'standard_1',
            name: "Standard",
            description: "Guided four-part response"
        },
        {
            id: 'yesno_1',
            name: "Yes/No",
            description: "Simple \"yes\" or \"no\" response"
        }
    ];

    $scope.$on('EditSaved', function(event, model) {
        $location.url(format(
            '/measure/{}?survey={}', model.id, $scope.survey.id));
    });
    $scope.$on('EditDeleted', function(event, model) {
        $location.url(format(
            '/subprocess/{}?survey={}', $scope.subprocess.id, $scope.survey.id));
    });

    $scope.checkRole = authz(current, $scope.survey);
}])


;
