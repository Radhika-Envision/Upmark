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
                case 'assessment_add':
                    return Roles.hasPermission(current.user.role, 'clerk');
                    break;
                case 'assessment_browse':
                    return Roles.hasPermission(current.user.role, 'clerk') ||
                        Roles.hasPermission(current.user.role, 'consultant');
                    break;
                default:
                    return Roles.hasPermission(current.user.role, 'author');
            }
        };
    };
}])


.controller('SurveyCtrl', [
        '$scope', 'Survey', 'routeData', 'Editor', 'questionAuthz', 'hotkeys',
        '$location', 'Notifications', 'Current', 'Hierarchy', 'layout',
        'format', '$http', 'Numbers', 'Organisation', 'Assessment',
        function($scope, Survey, routeData, Editor, authz, hotkeys,
                 $location, Notifications, current, Hierarchy, layout, format,
                 $http, Numbers, Organisation, Assessment) {

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
        var ids = {};
        for (var i = 0; i < rt.parts.length; i++) {
            ids[rt.parts[i].id] = true;
        }
        var id;
        for (var i = 0; i <= rt.parts.length; i++) {
            id = Numbers.idOf(i);
            if (!ids[id])
                break;
        }
        var part = {
            id: id,
            name: 'Response part ' + id.toUpperCase(),
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

    $scope.aSearch = {
        organisation: current.user.organisation
    };
    $scope.searchOrg = function(term) {
        Organisation.query({term: term}).$promise.then(function(orgs) {
            $scope.organisations = orgs;
        });
    };
    $scope.$watch('aSearch.organisation', function(organisation) {
        Assessment.query({orgId: organisation.id, surveyId: $scope.survey.id}).$promise.then(
            function success(assessments) {
                $scope.assessments = assessments;
            },
            function failure(details) {
                Notifications.set('survey', 'error',
                    "Could not get assessment list: " + details.statusText);
            }
        );
    });

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


.controller('SurveyImportCtrl', [
        '$scope', 'Survey', 'hotkeys', '$location', '$timeout',
        'Notifications', 'layout', 'format', '$http', '$cookies',
        function($scope, Survey, hotkeys, $location, $timeout,
                 Notifications, layout, format, $http, $cookies) {

    $scope.progress = {
        isWorking: false,
        isFinished: false,
        uploadFraction: 0.0
    };
    Notifications.remove('import');
    $scope.survey = {
        title: "Aquamark Import",
        description: ""
    };

    var headers = {};
    var xsrfName = $http.defaults.xsrfHeaderName;
    headers[xsrfName] = $cookies.get($http.defaults.xsrfCookieName);

    var config = {
        url: '/import/structure.json',
        maxFilesize: 50,
        paramName: "file",
        acceptedFiles: ".xls,.xlsx",
        headers: headers,
        autoProcessQueue: false
    };

    Dropzone.autoDiscover = false;
    var dropzone = new Dropzone("#dropzone", config);

    $scope.import = function() {
        if (!dropzone.files.length) {
            Notifications.set('import', 'error', "Please choose a file");
            return;
        }
        $scope.progress.isWorking = true;
        $scope.progress.isFinished = false;
        $scope.progress.uploadFraction = 0.0;
        dropzone.processQueue();
    };

    $scope.reset = function() {
        dropzone.processQueue();
    }

    dropzone.on('sending', function(file, xhr, formData) {
        formData.append('title', $scope.survey.title);
        formData.append('description', $scope.survey.description);
    });

    dropzone.on('uploadprogress', function(file, progress) {
        console.log(progress);
        $scope.progress.uploadFraction = progress / 100;
        $scope.$apply();
    });

    dropzone.on("success", function(file, response) {
        Notifications.set('import', 'success', "Import finished", 5000);
        $timeout(function() {
            $scope.progress.isFinished = true;
        }, 1000);
        $timeout(function() {
            $location.url('/survey/' + response);
        }, 5000);
    });

    dropzone.on('addedfile', function(file) {
        if (dropzone.files.length > 1)
            dropzone.removeFile(dropzone.files[0]);
    });

    dropzone.on("error", function(file, details, request) {
        var error;
        if (request) {
            error = "Import failed: " + request.statusText;
        } else {
            error = details;
        }
        dropzone.removeAllFiles();
        Notifications.set('import', 'error', error);
        $scope.progress.isWorking = false;
        $scope.progress.isFinished = false;
        $scope.$apply();
    });

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
    return function(entity, assessment) {
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
            if (stack[1].responseType !== undefined) {
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

        if (assessment) {
            // Assessments take the place of the hierarchy.
            hstack[1] = {
                path: 'assessment',
                title: 'Assessments',
                label: 'A',
                entity: assessment,
                level: 'h'
            };
        }

        var qnodes = [];
        if (stack.length > 2 && hierarchy) {
            var qnodeMaxIndex = stack.length - 1;
            if (stack[stack.length - 1].responseType !== undefined) {
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
            assessment: assessment,
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
            entity: '=',
            assessment: '='
        },
        replace: true,
        templateUrl: 'question_header.html',
        controller: ['$scope', 'layout', 'Structure', 'hotkeys', 'format',
                '$location',
                function($scope, layout, Structure, hotkeys, format, $location) {
            $scope.layout = layout;
            $scope.$watchGroup(['entity', 'assessment'], function(vals) {
                $scope.structure = Structure(vals[0], vals[1]);
                $scope.currentItem = $scope.structure.hstack[
                    $scope.structure.hstack.length - 1];
                $scope.upItem = $scope.structure.hstack[
                    $scope.structure.hstack.length - 2];
            });

            $scope.itemUrl = function(item, accessor) {
                if (!item)
                    return "";

                var accessor = accessor || 'id';
                var key = item.entity[accessor];

                if (!key)
                    return "";

                var path = format("#/{}/{}", item.path, key);
                var query = [];
                if (item.path != 'survey' && item.path != 'assessment') {
                    if ($scope.assessment)
                        query.push('assessment=' + $scope.assessment.id);
                    else
                        query.push('survey=' + $scope.structure.survey.id);
                }
                if (item.path == 'measure' && item.entity.parent) {
                    query.push('parent=' + item.entity.parent.id);
                }
                path += '?' + query.join('&');

                return path;
            };

            hotkeys.bindTo($scope)
                .add({
                    combo: ['u'],
                    description: "Go up one level of the hierarchy",
                    callback: function(event, hotkey) {
                        var url = $scope.itemUrl($scope.upItem);
                        if (!url)
                            url = '/surveys';
                        $location.url(url.substring(1));
                    }
                })
                .add({
                    combo: ['p'],
                    description: "Go to the previous category or measure",
                    callback: function(event, hotkey) {
                        var url = $scope.itemUrl($scope.currentItem, 'prev');
                        if (!url)
                            return;
                        $location.url(url.substring(1));
                    }
                })
                .add({
                    combo: ['n'],
                    description: "Go to the next category or measure",
                    callback: function(event, hotkey) {
                        var url = $scope.itemUrl($scope.currentItem, 'next');
                        if (!url)
                            return;
                        $location.url(url.substring(1));
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

    $scope.qnodeUrl = function(item, $index) {
        return format("/qnode/{}?survey={}&hierarchy={}",
            item.id, $scope.survey.id, $scope.hierarchy.id);
    };

    $scope.checkRole = authz(current, $scope.survey);
    $scope.QuestionNode = QuestionNode;
    $scope.Hierarchy = Hierarchy;
}])


.controller('QuestionNodeCtrl', [
        '$scope', 'QuestionNode', 'routeData', 'Editor', 'questionAuthz',
        '$location', 'Notifications', 'Current', 'format', 'Structure',
        'layout', 'Arrays',
        function($scope, QuestionNode, routeData, Editor, authz,
                 $location, Notifications, current, format, Structure,
                 layout, Arrays) {

    // routeData.parent and routeData.hierarchy will only be defined when
    // creating a new qnode.

    $scope.layout = layout;
    $scope.assessment = routeData.assessment;
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

    $scope.structure = Structure($scope.qnode);
    $scope.survey = $scope.structure.survey;
    $scope.edit = Editor('qnode', $scope, {
        parentId: routeData.parent && routeData.parent.id,
        hierarchyId: routeData.hierarchy && routeData.hierarchy.id,
        surveyId: $scope.survey.id
    });
    if (!$scope.qnode.id)
        $scope.edit.edit();

    var levels = $scope.structure.hierarchy.structure.levels;
    $scope.currentLevel = levels[$scope.structure.qnodes.length - 1];
    $scope.nextLevel = levels[$scope.structure.qnodes.length];

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

    $scope.qnodeUrl = function(item, $index) {
        var query;
        if ($scope.assessment)
            query = 'assessment=' + $scope.assessment.id;
        else
            query = 'survey=' + $scope.survey.id;
        return format("/qnode/{}?{}", item.id, query);
    };

    $scope.measureUrl = function(item, $index) {
        var query = 'parent=' + $scope.qnode.id;
        if ($scope.assessment)
            query += '&assessment=' + $scope.assessment.id;
        else
            query += '&survey=' + $scope.survey.id;
        return format("/measure/{}?{}", item.id, query);
    };

    $scope.checkRole = authz(current, $scope.survey);
    $scope.editable = ($scope.survey.isEditable &&
        !$scope.assessment && $scope.checkRole('survey_node_edit'));
}])


.controller('QnodeChildren', ['$scope', 'bind', 'Editor', 'QuestionNode',
        function($scope, bind, Editor, QuestionNode) {

    bind($scope, 'children', $scope, 'model', true);

    $scope.edit = Editor('model', $scope, {}, QuestionNode);
    $scope.$on('EditSaved', function(event, model) {
        event.stopPropagation();
    });

    $scope.dragOpts = {
        axis: 'y',
        handle: '.grab-handle'
    };

    $scope.$watchGroup(['survey', 'assessment', 'qnode'], function() {
        if ($scope.assessment)
            $scope.query = 'assessment=' + $scope.assessment.id;
        else
            $scope.query = 'survey=' + $scope.survey.id;

        $scope.edit.params = {
            surveyId: $scope.survey.id,
            parentId: $scope.qnode.id
        }
    });
}])


.controller('QnodeMeasures', ['$scope', 'bind', 'Editor', 'Measure', 'Response',
        'Notifications',
        function($scope, bind, Editor, Measure, Response, Notifications) {

    bind($scope, 'measures', $scope, 'model', true);

    $scope.edit = Editor('model', $scope, {}, Measure);
    $scope.$on('EditSaved', function(event, model) {
        event.stopPropagation();
    });

    $scope.dragOpts = {
        axis: 'y',
        handle: '.grab-handle'
    };

    if ($scope.assessment)
        $scope.query = 'assessment=' + $scope.assessment.id;
    else
        $scope.query = 'survey=' + $scope.survey.id;
    $scope.query += "&parent=" + $scope.qnode.id;

    $scope.edit.params = {
        surveyId: $scope.survey.id,
        qnodeId: $scope.qnode.id
    }

    if ($scope.assessment) {
        // Get the responses that are associated with this qnode and assessment.
        Response.query({
            assessmentId: $scope.assessment.id,
            qnodeId: $scope.qnode.id
        }).$promise.then(
            function success(responses) {
                var rmap = {};
                for (var i = 0; i < responses.length; i++) {
                    var response = responses[i];
                    rmap[response.measure.id] = response;
                }
                $scope.responseMap = rmap;
            },
            function failure(details) {
                Notifications.set('edit', 'error',
                    "Could not get aggregate scores: " +
                    details.statusText);
            }
        );
    }
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
        'Structure', 'Arrays', 'Response', 'hotkeys',
        function($scope, Measure, routeData, Editor, authz,
                 $location, Notifications, current, Survey, format, layout,
                 Structure, Arrays, Response, hotkeys) {

    $scope.layout = layout;
    $scope.parent = routeData.parent;
    $scope.assessment = routeData.assessment;
    if (routeData.measure) {
        // Editing old
        $scope.measure = routeData.measure;
    } else {
        // Creating new
        $scope.measure = new Measure({
            parent: routeData.parent,
            survey: routeData.survey,
            weight: 100,
            responseType: null
        });
    }

    if ($scope.assessment) {
        // Get the response that is associated with this measure and assessment.
        // Create an empty one if it doesn't exist yet.
        $scope.response = Response.get({
            measureId: $scope.measure.id,
            assessmentId: $scope.assessment.id
        });
        $scope.response.$promise.catch(function failure(details) {
            if (details.status != 404) {
                Notifications.set('edit', 'error',
                    "Failed to get response details: " + details.statusText);
                return;
            }
            $scope.response = new Response({
                measureId: $scope.measure.id,
                assessmentId: $scope.assessment.id,
                responseParts: [],
                comment: '',
                notRelevant: false,
                approval: 'draft'
            });
        });
    }
    $scope.saveResponse = function() {
        $scope.response.$save().then(
            function success() {
                Notifications.set('edit', 'success', "Saved", 5000);
            },
            function failure(details) {
                Notifications.set('edit', 'error',
                    "Could not save response: " + details.statusText);
            });
    };
    $scope.setState = function(state) {
        $scope.response.$save({approval: state},
            function success() {
                Notifications.set('edit', 'success', "Saved", 5000);
            },
            function failure(details) {
                Notifications.set('edit', 'error',
                    "Could not save response: " + details.statusText);
            }
        );
    };

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
        // Do a little processing on the response types
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

    if ($scope.assessment) {
        var t_approval;
        if (current.user.role == 'clerk' || current.user.role == 'org_admin')
            t_approval = 'final';
        else if (current.user.role == 'consultant')
            t_approval = 'reviewed';
        else
            t_approval = 'approved';
        hotkeys.bindTo($scope)
            .add({
                combo: ['ctrl+enter'],
                description: "Save the response, and mark it as " + t_approval,
                callback: function(event, hotkey) {
                    $scope.setState(t_approval);
                }
            });
    }
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
