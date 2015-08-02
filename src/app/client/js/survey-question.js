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


.factory('Structure', function() {
    return function(entity) {
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
                path: 'survey',
                title: 'Surveys',
                label: 'S',
                entity: stack[0],
                level: 0
            });
        }
        // Hierarchy
        if (stack.length > 1) {
            hstack.push({
                path: 'hierarchy',
                title: 'Question Sets',
                label: 'Qs',
                entity: stack[1],
                level: 1
            });
        }

        var measure = null;
        var qnodes = [];
        if (stack.length > 2) {
            var qnodeMaxIndex = stack.length - 1;
            if (stack[stack.length - 1].responseType) {
                measure = stack[stack.length - 1];
                qnodeMaxIndex = stack.length - 2;
            } else {
                measure = null;
                qnodeMaxIndex = stack.length - 1;
            }

            var structure = stack[1].structure;
            // Qnodes and measures
            for (var i = 2; i <= qnodeMaxIndex; i++) {
                entity = stack[i];
                var level = structure.levels[i - 2];
                hstack.push({
                    path: 'qnode',
                    title: level.title,
                    label: level.label,
                    entity: entity,
                    level: i
                });
                qnodes.push(entity);
            }

            if (measure) {
                hstack.push({
                    path: 'measure',
                    title: structure.measure.title,
                    label: structure.measure.label,
                    entity: stack[stack.length - 1],
                    level: stack.length - 1
                });
            }
        }

        return {
            survey: stack[0] || null,
            hierarchy: stack[1] || null,
            qnodes: qnodes,
            measure: measure,
            hstack: hstack
        };
    };
})


.directive('questionHeader', [function() {
    return {
        restrict: 'E',
        scope: {
            entity: '='
        },
        replace: true,
        templateUrl: 'question_header.html',
        controller: ['$scope', 'layout', 'Structure',
                function($scope, layout, Structure) {
            $scope.layout = layout;
            $scope.$watch('entity', function(entity) {
                $scope.structure = Structure(entity);
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


.controller('QuestionNodeCtrl', [
        '$scope', 'QuestionNode', 'routeData', 'Editor', 'questionAuthz',
        '$location', 'Notifications', 'Current', 'format', 'Structure',
        'Measure', 'layout',
        function($scope, QuestionNode, routeData, Editor, authz,
                 $location, Notifications, current, format, Structure,
                 Measure, layout) {

    // routeData.parent and routeData.hierarchy will only be defined when
    // creating a new qnode.

    $scope.layout = layout;
    if (routeData.qnode) {
        // Editing old
        $scope.qnode = routeData.qnode;
        $scope.children = routeData.children;
        $scope.measures = routeData.measures;
    } else {
        // Creating new
        $scope.qnode = new QuestionNode({
            'parent': routeData.parent,
            'hierarchy': routeData.hierarchy
        });
        $scope.children = null;
        $scope.measures = null;
    }

    $scope.$watch('qnode', function(qnode) {
        $scope.structure = Structure(qnode);
        $scope.survey = $scope.structure.survey;
        $scope.edit = Editor('qnode', $scope, {
            parentId: routeData.parent && routeData.parent.id,
            hierarchyId: routeData.hierarchy && routeData.hierarchy.id,
            surveyId: $scope.survey.id
        });
        if (!qnode.id)
            $scope.edit.edit();

        var levels = $scope.structure.hierarchy.structure.levels;
        $scope.currentLevel = levels[$scope.structure.qnodes.length - 1];
        $scope.nextLevel = levels[$scope.structure.qnodes.length];
    });

    $scope.$on('EditSaved', function(event, model) {
        $location.url(format(
            '/qnode/{}?survey={}', model.id, $scope.survey.id));
    });
    $scope.$on('EditDeleted', function(event, model) {
        if (model.parent) {
            $location.url(format(
                '/qnode/{}?survey={}', model.parent.id,
                $scope.survey.id));
        } else {
            $location.url(format(
                '/hierarchy/{}?survey={}', model.hierarchy.id,
                $scope.survey.id));
        }
    });

    $scope.checkRole = authz(current, $scope.survey);
    $scope.QuestionNode = QuestionNode;
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
