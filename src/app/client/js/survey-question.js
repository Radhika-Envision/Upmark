'use strict';

angular.module('wsaa.surveyQuestions', [
    'ngResource', 'ngSanitize', 'ui.select', 'ui.tree', 'ui.sortable',
    'wsaa.admin'])


.factory('Survey', ['$resource', function($resource) {
    return $resource('/survey/:id.json', {id: '@id'}, {
        get: { method: 'GET', cache: false },
        create: { method: 'POST' },
        save: { method: 'PUT' },
        query: { method: 'GET', isArray: true, cache: false },
        history: { method: 'GET', url: '/survey/:id/history.json',
            isArray: true, cache: false }
    });
}])


.factory('Hierarchy', ['$resource', function($resource) {
    return $resource('/hierarchy/:id.json', {id: '@id'}, {
        get: { method: 'GET', cache: false },
        create: { method: 'POST' },
        save: { method: 'PUT' },
        query: { method: 'GET', isArray: true, cache: false },
        history: { method: 'GET', url: '/hierarchy/:id/survey.json',
            isArray: true, cache: false }
    });
}])


.factory('QuestionNode', ['$resource', function($resource) {
    return $resource('/qnode/:id.json', {id: '@id'}, {
        get: { method: 'GET', cache: false },
        create: { method: 'POST' },
        save: { method: 'PUT' },
        query: { method: 'GET', isArray: true, cache: false },
        reorder: { method: 'PUT', isArray: true },
        history: { method: 'GET', url: '/qnode/:id/survey.json',
            isArray: true, cache: false }
    });
}])


.factory('Measure', ['$resource', function($resource) {
    return $resource('/measure/:id.json', {id: '@id'}, {
        get: { method: 'GET', cache: false },
        create: { method: 'POST' },
        save: { method: 'PUT' },
        query: { method: 'GET', isArray: true, cache: false },
        reorder: { method: 'PUT', isArray: true },
        history: { method: 'GET', url: '/measure/:id/survey.json',
            isArray: true, cache: false }
    });
}])


.factory('questionAuthz', ['Roles', function(Roles) {
    return function(current, survey) {
        return function(functionName) {
            switch(functionName) {
                case 'survey_dup':
                case 'survey_state':
                    return Roles.hasPermission(current.user.role, 'admin');
                    break;
            }
            return Roles.hasPermission(current.user.role, 'author');
        };
    };
}])


.controller('SurveyCtrl', [
        '$scope', 'Survey', 'routeData', 'Editor', 'questionAuthz', 'hotkeys',
        '$location', 'Notifications', 'Current', 'Hierarchy', 'layout',
        'format', '$http',
        function($scope, Survey, routeData, Editor, authz, hotkeys,
                 $location, Notifications, current, Hierarchy, layout, format,
                 $http) {

    $scope.layout = layout;
    if (routeData.survey) {
        // Viewing old
        $scope.edit = Editor('survey', $scope);
        $scope.survey = routeData.survey;
        $scope.hierarchies = routeData.hierarchies;
        $scope.duplicating = false;
    } else if (routeData.duplicate) {
        // Duplicating existing
        $scope.edit = Editor('survey', $scope,
            {duplicateId: routeData.duplicate.id});
        $scope.survey = routeData.duplicate;
        $scope.survey.id = null;
        $scope.survey.title = $scope.survey.title + " (duplicate)"
        $scope.hierarchies = null;
        $scope.edit.edit();
        $scope.duplicating = true;
    } else {
        // Creating new
        $scope.edit = Editor('survey', $scope);
        $scope.survey = new Survey({
            responseTypes: []
        });
        $scope.hierarchies = null;
        $scope.edit.edit();
        $http.get('/default_response_types.json').then(
            function success(response) {
                $scope.edit.model.responseTypes = response.data;
            },
            function failure(details) {
                Notifications.set('edit', 'warning',
                    "Could not get response types: " + details.statusText);
            }
        );
        $scope.duplicating = false;
    }

    $scope.rtEdit = {};
    $scope.editRt = function(model, index) {
        $scope.rtEdit = {
            model: model,
            rt: angular.copy(model.responseTypes[index]),
            i: index
        };
    };
    $scope.saveRt = function() {
        var rts = $scope.rtEdit.model.responseTypes;
        rts[$scope.rtEdit.i] = angular.copy($scope.rtEdit.rt);
        $scope.rtEdit = {};
    };
    $scope.cancelRt = function() {
        $scope.rtEdit = {};
    };
    $scope.addRt = function(model) {
        var i = model.responseTypes.length + 1;
        model.responseTypes.push({
            id: 'response_' + i,
            name: 'Response Type ' + i,
            parts: []
        })
    };
    $scope.addPart = function(rt) {
        var i = rt.parts.length + 1;
        var part = {
            id: 'part_' + i,
            name: 'Response part ' + i,
            options: [
                {score: 0, name: 'No', 'if': null},
                {score: 1, name: 'Yes', 'if': null}
            ]
        };
        rt.parts.push(part);
        $scope.updateFormula(rt);
    };
    $scope.addOption = function(part) {
        part.options.push({
            score: 0,
            name: 'Option ' + (part.options.length + 1)
        })
    };
    $scope.updateFormula = function(rt) {
        if (rt.parts.length <= 1) {
            rt.formula = null;
            return;
        }
        var formula = "";
        for (var i = 0; i < rt.parts.length; i++) {
            var part = rt.parts[i];
            if (i > 0)
                formula += " + ";
            if (part.id)
                formula += part.id;
            else
                formula += "?";
        }
        rt.formula = formula;
    };
    $scope.remove = function(rt, list, item) {
        var i = list.indexOf(item);
        if (i < 0)
            return;
        list.splice(i, 1);
        if (item.options)
            $scope.updateFormula(rt);
    };

    $scope.$on('EditSaved', function(event, model) {
        $location.url('/survey/' + model.id);
    });
    $scope.$on('EditDeleted', function(event, model) {
        $location.url('/surveys');
    });

    $scope.checkRole = authz(current, $scope.survey);

    $scope.toggleOpen = function() {
        $scope.survey.$save({open: !$scope.survey.isOpen},
            function success() {
                Notifications.set('edit', 'success', "Saved", 5000);
            },
            function failure(details) {
                Notifications.set('edit', 'error',
                    "Could not save object: " + details.statusText);
            }
        );
    };
    $scope.toggleEditable = function() {
        $scope.survey.$save({editable: !$scope.survey.isEditable},
            function success() {
                Notifications.set('edit', 'success', "Saved", 5000);
            },
            function failure(details) {
                Notifications.set('edit', 'error',
                    "Could not save object: " + details.statusText);
            }
        );
    };

    $scope.Survey = Survey;

    hotkeys.bindTo($scope)
        .add({
            combo: ['a'],
            description: "Add a new question set",
            callback: function(event, hotkey) {
                $location.url(
                    format("/hierarchy/new?survey={{}}", $scope.survey.id));
            }
        })
        .add({
            combo: ['s'],
            description: "Search for measures",
            callback: function(event, hotkey) {
                $location.url(
                    format("/measures?survey={{}}", $scope.survey.id));
            }
        });
}])


.controller('SurveyListCtrl', ['$scope', 'questionAuthz', 'Survey', 'Current',
        'layout',
        function($scope, authz, Survey, current, layout) {

    $scope.layout = layout;
    $scope.checkRole = authz(current, null);

    $scope.search = {
        term: "",
        open: !$scope.checkRole('survey_edit'),
        editable: $scope.checkRole('survey_edit'),
        page: 0,
        pageSize: 10
    };
    $scope.$watch('search', function(search) {
        Survey.query(search).$promise.then(function(surveys) {
            $scope.surveys = surveys;
        });
    }, true);
}])


/**
 * Drop-down menu to navigate to old versions of an entity.
 */
.directive('surveyHistory', [function() {
    return {
        restrict: 'E',
        templateUrl: '/survey_history.html',
        scope: {
            entity: '=',
            service: '='
        },
        controller: ['$scope', '$location', function($scope, $location) {
            $scope.toggled = function(open) {
                if (open) {
                    $scope.surveys = $scope.service.history({
                        id: $scope.entity.id
                    });
                }
            };

            $scope.navigate = function(survey) {
                if ($scope.entity.isOpen != null)
                    $location.url('/survey/' + survey.id);
                else
                    $location.search('survey', survey.id);
            };
            $scope.isActive = function(survey) {
                if ($scope.entity.isOpen != null)
                    return $location.url().indexOf('/survey/' + survey.id) >= 0;
                else
                    return $location.search().survey == survey.id;
            };
        }]
    };
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

        var hstack = [];
        var survey = null;
        var hierarchy = null;
        var measure = null;
        // Survey
        if (stack.length > 0) {
            survey = stack[0];
            hstack.push({
                path: 'survey',
                title: 'Surveys',
                label: 'S',
                entity: survey,
                level: 's'
            });
        }
        // Hierarchy, or orphaned measure
        if (stack.length > 1) {
            if (stack[1].responseType) {
                measure = stack[1];
                hstack.push({
                    path: 'measure',
                    title: 'Measures',
                    label: 'M',
                    entity: measure,
                    level: 'm'
                });
            } else {
                hierarchy = stack[1];
                hstack.push({
                    path: 'hierarchy',
                    title: 'Question Sets',
                    label: 'Qs',
                    entity: hierarchy,
                    level: 'h'
                });
            }
        }

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

            var structure = hierarchy.structure;
            // Qnodes and measures
            for (var i = 2; i <= qnodeMaxIndex; i++) {
                entity = stack[i];
                var level = structure.levels[i - 2];
                hstack.push({
                    path: 'qnode',
                    title: level.title,
                    label: level.label,
                    entity: entity,
                    level: i - 2
                });
                qnodes.push(entity);
            }

            if (measure) {
                hstack.push({
                    path: 'measure',
                    title: structure.measure.title,
                    label: structure.measure.label,
                    entity: measure,
                    level: 'm'
                });
            }
        }

        return {
            survey: survey,
            hierarchy: hierarchy,
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
        controller: ['$scope', 'layout', 'Structure', 'hotkeys', 'format',
                '$location',
                function($scope, layout, Structure, hotkeys, format, $location) {
            $scope.layout = layout;
            $scope.$watch('entity', function(entity) {
                $scope.structure = Structure(entity);
            });

            hotkeys.bindTo($scope)
                .add({
                    combo: ['ctrl+up'],
                    description: "Go up one level of the hierarchy",
                    callback: function(event, hotkey) {
                        var item = $scope.structure.hstack[
                            $scope.structure.hstack.length - 2]
                        var path = format(
                            "/{}/{}", item.path, item.entity.id);
                        if (item.path != 'survey')
                            path += '?survey=' + $scope.structure.survey.id;
                        $location.url(path);
                    }
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
    $scope.Hierarchy = Hierarchy;
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


.controller('MeasureLinkCtrl', [
        '$scope', 'QuestionNode', 'routeData', 'questionAuthz',
        '$location', 'Notifications', 'Current', 'format',
        'Measure', 'layout',
        function($scope, QuestionNode, routeData, authz,
                 $location, Notifications, current, format,
                 Measure, layout) {

    $scope.layout = layout;
    $scope.qnode = routeData.parent;
    $scope.survey = routeData.survey;

    $scope.measure = {
        parent: $scope.qnode,
        responseType: "dummy"
    };

    $scope.select = function(measure) {
        // postData is empty: we don't want to update the contents of the
        // measure; just its links to parents (giving in query string).
        var postData = {};
        Measure.save({
            id: measure.id,
            parentId: $scope.qnode.id,
            surveyId: $scope.survey.id
        }, postData).$promise.then(
            function success(measure) {
                Notifications.set('edit', 'success', "Saved", 5000);
                $location.url(format(
                    '/qnode/{}?survey={}', $scope.qnode.id, $scope.survey.id));
            },
            function failure(details) {
                Notifications.set('edit', 'error',
                    "Could not save object: " + details.statusText);
            }
        );
    };

    $scope.search = {
        term: "",
        surveyId: $scope.survey.id,
        page: 0,
        pageSize: 10
    };
    $scope.$watch('search', function(search) {
        Measure.query(search).$promise.then(function(measures) {
            $scope.measures = measures;
        });
    }, true);

    $scope.checkRole = authz(current, $scope.survey);
    $scope.QuestionNode = QuestionNode;
    $scope.Measure = Measure;
}])


.controller('MeasureCtrl', [
        '$scope', 'Measure', 'routeData', 'Editor', 'questionAuthz',
        '$location', 'Notifications', 'Current', 'Survey', 'format', 'layout',
        'Structure', 'Arrays',
        function($scope, Measure, routeData, Editor, authz,
                 $location, Notifications, current, Survey, format, layout,
                 Structure, Arrays) {

    $scope.layout = layout;
    $scope.parent = routeData.parent;
    if (routeData.measure) {
        // Editing old
        $scope.measure = routeData.measure;
    } else {
        // Creating new
        $scope.measure = new Measure({
            parent: routeData.parent,
            survey: routeData.survey,
            weight: 100,
            responseType: 'standard_1'
        });
    }

    $scope.$watch('measure', function(measure) {
        $scope.structure = Structure(measure);
        $scope.survey = $scope.structure.survey;
        $scope.edit = Editor('measure', $scope, {
            parentId: $scope.parent && $scope.parent.id,
            surveyId: $scope.survey.id
        });
        if (!measure.id)
            $scope.edit.edit();

        if (measure.parents) {
            var parents = [];
            for (var i = 0; i < measure.parents.length; i++) {
                parents.push(Structure(measure.parents[i]));
            }
            $scope.parents = parents;
        }
    });
    $scope.$watch('structure.survey', function(survey) {
        if (!survey.responseTypes)
            return;
        var responseType = null;
        var responseTypes = angular.copy(survey.responseTypes);
        for (var i = 0; i < responseTypes.length; i++) {
            var t = responseTypes[i];
            if (t.parts.length == 0) {
                t.description = "No parts";
            } else {
                if (t.parts.length == 1) {
                    t.description = "1 part";
                } else {
                    t.description = "" + t.parts.length + " parts";
                }
                var optNames = t.parts[0].options.map(function(o) {
                    return o.name;
                });
                optNames = optNames.filter(function(n) {
                    return !!n;
                });
                optNames = optNames.join(', ');
                if (optNames)
                    t.description += ': ' + optNames;
                if (t.parts.length > 1)
                    t.description += ' etc.';
            }
        }
        $scope.responseTypes = responseTypes;
    });
    $scope.$watchGroup(['measure.responseType', 'structure.survey.responseTypes'],
                       function(vars) {
        var rtId = vars[0];
        var rts = vars[1];
        var i = Arrays.indexOf(rts, rtId, 'id', null);
        $scope.responseType = rts[i];
    });

    $scope.$on('EditSaved', function(event, model) {
        if (model.parent) {
            $location.url(format(
                '/measure/{}?survey={}&parent={}', model.id, $scope.survey.id,
                $scope.parent.id));
        } else {
            $location.url(format(
                '/measure/{}?survey={}', model.id, $scope.survey.id));
        }
    });
    $scope.$on('EditDeleted', function(event, model) {
        if (model.parent) {
            $location.url(format(
                '/qnode/{}?survey={}', model.parent.id, $scope.survey.id));
        } else {
            $location.url(format(
                '/measures?survey={}', $scope.survey.id));
        }
    });

    $scope.checkRole = authz(current, $scope.survey);
    $scope.Measure = Measure;
}])


.controller('MeasureListCtrl', ['$scope', 'questionAuthz', 'Measure', 'Current',
        'layout', 'routeData',
        function($scope, authz, Measure, current, layout, routeData) {

    $scope.layout = layout;
    $scope.checkRole = authz(current, null);
    $scope.survey = routeData.survey;

    $scope.search = {
        term: "",
        surveyId: $scope.survey && $scope.survey.id,
        orphan: null,
        page: 0,
        pageSize: 10
    };
    $scope.$watch('search', function(search) {
        Measure.query(search).$promise.then(function(measures) {
            $scope.measures = measures;
        });
    }, true);

    $scope.cycleOrphan = function() {
        switch ($scope.search.orphan) {
            case true:
                $scope.search.orphan = null;
                break;
            case null:
                $scope.search.orphan = false;
                break;
            case false:
                $scope.search.orphan = true;
                break;
        }
    };
}])


;
