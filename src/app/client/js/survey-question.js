'use strict';

angular.module('wsaa.surveyQuestions', [
    'ngResource', 'ngSanitize', 'ui.select', 'ui.tree', 'ui.sortable',
    'wsaa.admin'])


.factory('Survey', ['$resource', 'paged', function($resource, paged) {
    return $resource('/survey/:id.json', {id: '@id'}, {
        get: { method: 'GET', cache: false },
        create: { method: 'POST' },
        save: { method: 'PUT' },
        query: {
            method: 'GET', isArray: true, cache: false,
            interceptor: {response: paged}
        },
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


.factory('Measure', ['$resource', 'paged', function($resource, paged) {
    return $resource('/measure/:id.json', {id: '@id'}, {
        get: { method: 'GET', cache: false },
        create: { method: 'POST' },
        save: { method: 'PUT' },
        query: {
            method: 'GET', isArray: true, cache: false,
            interceptor: {response: paged}
        },
        reorder: { method: 'PUT', isArray: true },
        history: { method: 'GET', url: '/measure/:id/survey.json',
            isArray: true, cache: false }
    });
}])


.factory('Attachment', ['$resource', function($resource) {
    return $resource('/assessment/:assessmentId/measure/:measureId/attachment.json',
            {assessmentId: '@assessmentId', measureId: '@measureId'}, {
        saveExternals: { method: 'PUT', isArray: true },
        query: { method: 'GET', isArray: true, cache: false },
        remove: { method: 'DELETE', url: '/attachment/:id.json', cache: false }
    });
}])


.factory('Statistics', ['$resource', function($resource) {
    return $resource('/statistics/:id.json', {id: '@id'}, {
        get: { method: 'GET', isArray: true, cache: false }
    });
}])


.factory('questionAuthz', ['Roles', function(Roles) {
    return function(current, survey, assessment) {
        var ownOrg = false;
        var org = assessment && assessment.organisation || null;
        if (org)
            ownOrg = org.id == current.user.organisation.id;
        else
            ownOrg = true;
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
                case 'assessment_review':
                    return Roles.hasPermission(current.user.role, 'consultant');
                    break;
                case 'view_aggregate_score':
                case 'view_single_score':
                    if (Roles.hasPermission(current.user.role, 'consultant'))
                        return true;
                    if (Roles.hasPermission(current.user.role, 'org_admin'))
                        return ownOrg;
                    return false;
                    break;
                case 'assessment_admin':
                    if (Roles.hasPermission(current.user.role, 'consultant'))
                        return true;
                    if (Roles.hasPermission(current.user.role, 'org_admin'))
                        return ownOrg;
                    break;
                case 'assessment_edit':
                case 'view_response':
                case 'alter_response':
                    if (Roles.hasPermission(current.user.role, 'consultant'))
                        return true;
                    if (Roles.hasPermission(current.user.role, 'clerk'))
                        return ownOrg;
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


.directive('assessmentHeader', [function() {
    return {
        templateUrl: 'assessment_header.html',
        replace: true,
        scope: true,
        controller: ['$scope', function($scope) {
            $scope.showAssessmentChooser = false;
            $scope.toggleDropdown = function() {
                $scope.showAssessmentChooser = !$scope.showAssessmentChooser;
            };
        }]
    }
}])


.directive('assessmentSelect', [function() {
    return {
        restrict: 'AEC',
        templateUrl: 'assessment_select.html',
        scope: true,
        controller: ['$scope', 'Current', 'Assessment', 'Organisation',
                '$location', 'format', 'Notifications',
                function($scope, current, Assessment, Organisation,
                         $location, format, Notifications) {
            $scope.aSearch = {
                organisation: null
            };

            $scope.$watch('assessment.organisation', function(org) {
                if (!org)
                    org = $scope.org || current.user.organisation;
                $scope.aSearch.organisation = org;
            });

            $scope.searchOrg = function(term) {
                Organisation.query({term: term}).$promise.then(function(orgs) {
                    $scope.organisations = orgs;
                });
            };
            $scope.$watch('aSearch.organisation', function(organisation) {
                if (organisation)
                    $scope.search.orgId = organisation.id;
                else
                    $scope.search.orgId = null;
            });

            $scope.$watch('structure.hierarchy', function(hierarchy) {
                $scope.search.hierarchyId = hierarchy && hierarchy.id;
            });

            $scope.$watch('structure.survey', function(survey) {
                $scope.search.surveyId = survey && survey.id;
            });

            $scope.search = {
                term: "",
                orgId: null,
                hierarchyId: null,
                surveyId: null,
                page: 0,
                pageSize: 10
            };
            $scope.$watch('search', function(search) {
                Assessment.query(search).$promise.then(
                    function success(assessments) {
                        $scope.assessments = assessments;
                    },
                    function failure(details) {
                        Notifications.set('survey', 'error',
                            "Could not get submission list: " + details.statusText);
                    }
                );
            }, true);

            // Allow parent controller to specify a special URL formatter - this
            // is so one can switch between assessments without losing one's
            // place in the hierarchy.
            if (!$scope.getAssessmentUrl) {
                $scope.getAssessmentUrl = function(assessment) {
                    if (assessment)
                        return format('/assessment/{}', assessment.id);
                    else
                        return format('/hierarchy/{}?survey={}',
                            $scope.structure.hierarchy.id,
                            $scope.structure.survey.id);
                };
            }
        }],
        link: function(scope, elem, attrs) {
            scope.showEdit = attrs.assessmentSelectShowEdit !== undefined;
        }
    }
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
                title: 'Program',
                label: 'Pg',
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
                    title: 'Surveys',
                    label: 'Sv',
                    entity: hierarchy,
                    level: 'h'
                });
            }
        }

        if (assessment) {
            // Assessments slot in after hierarchy.
            hstack.splice(2, 0, {
                path: 'assessment',
                title: 'Submissions',
                label: 'Sb',
                entity: assessment,
                level: 'h'
            });
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
                if (item.path == 'survey' || item.path == 'assessment') {
                } else if (item.path == 'hierarchy') {
                    query.push('survey=' + $scope.structure.survey.id);
                } else {
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


.controller('HierarchyChoiceCtrl', [
        '$scope', 'routeData', 'Structure', 'questionAuthz', 'Current',
        'Hierarchy', 'layout', '$location', 'Roles',
        function($scope, routeData, Structure, questionAuthz, current,
                 Hierarchy, layout, $location, Roles) {
    $scope.layout = layout;
    $scope.survey = routeData.survey;
    $scope.hierarchy = routeData.hierarchy;
    $scope.structure = Structure($scope.hierarchy);

    if (current.user.role == 'author')
        $location.path('/hierarchy/' + $scope.hierarchy.id);

    $scope.Hierarchy = Hierarchy;
    $scope.checkRole = questionAuthz(current, $scope.survey);
}])


.controller('HierarchyCtrl', [
        '$scope', 'Hierarchy', 'routeData', 'Editor', 'questionAuthz', 'layout',
        '$location', 'Current', 'format', 'QuestionNode', 'Structure',
        function($scope, Hierarchy, routeData, Editor, authz, layout,
                 $location, current, format, QuestionNode, Structure) {

    $scope.layout = layout;
    $scope.survey = routeData.survey;
    $scope.edit = Editor('hierarchy', $scope, {surveyId: $scope.survey.id});
    if (routeData.hierarchy) {
        // Editing old
        $scope.hierarchy = routeData.hierarchy;
        $scope.children = routeData.qnodes;
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
        $scope.children = null;
        $scope.edit.edit();
    }
    $scope.structure = Structure($scope.hierarchy);

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

    $scope.editable = ($scope.survey.isEditable &&
        $scope.checkRole('survey_node_edit'));
}])


.controller('QuestionNodeCtrl', [
        '$scope', 'QuestionNode', 'routeData', 'Editor', 'questionAuthz',
        '$location', 'Notifications', 'Current', 'format', 'Structure',
        'layout', 'Arrays', 'ResponseNode',
        function($scope, QuestionNode, routeData, Editor, authz,
                 $location, Notifications, current, format, Structure,
                 layout, Arrays, ResponseNode) {

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

    // Used to get history
    $scope.QuestionNode = QuestionNode;

    $scope.checkRole = authz(current, $scope.survey, $scope.assessment);
    $scope.editable = ($scope.survey.isEditable &&
        !$scope.assessment && $scope.checkRole('survey_node_edit'));

    if ($scope.assessment) {
        $scope.rnode = ResponseNode.get({
            assessmentId: $scope.assessment.id,
            qnodeId: $scope.qnode.id
        });
        $scope.rnode.$promise.catch(function failure(details) {
            if (details.status != 404) {
                Notifications.set('edit', 'error',
                    "Failed to get response details: " + details.statusText);
                return;
            }
            $scope.rnode = new ResponseNode({
                qnodeId: $scope.qnode.id,
                assessmentId: $scope.assessment.id,
                score: 0.0,
                nSubmitted: 0,
                nReviewed: 0,
                nApproved: 0,
                nNotRelevant: 0,
                notRelevant: false
            });
        });
        $scope.$watch('rnode', function(rnode) {
            if (!rnode)
                return;
            $scope.rnode = rnode;
            $scope.stats = {
                score: rnode.score,
                progressItems: [
                    {
                        name: 'Final',
                        value: rnode.nSubmitted,
                        fraction: rnode.nSubmitted / $scope.qnode.nMeasures
                    },
                    {
                        name: 'Reviewed',
                        value: rnode.nReviewed,
                        fraction: rnode.nReviewed / $scope.qnode.nMeasures
                    },
                    {
                        name: 'Approved',
                        value: rnode.nApproved,
                        fraction: rnode.nApproved / $scope.qnode.nMeasures
                    },
                ]
            };
        }, true);
    }

    $scope.getAssessmentUrl = function(assessment) {
        if (assessment) {
            return format('/qnode/{}?assessment={}',
                $scope.qnode.id, assessment.id);
        } else {
            return format('/qnode/{}?survey={}',
                $scope.qnode.id, $scope.survey.id);
        }
    };

    $scope.toggleNotRelevant = function() {
        var oldValue = $scope.rnode.notRelevant;
        $scope.rnode.notRelevant = !oldValue;
        $scope.rnode.$save().then(
            function success() {
                Notifications.set('edit', 'success', "Saved", 5000);
            },
            function failure(details) {
                $scope.rnode.notRelevant = oldValue;
                Notifications.set('edit', 'error',
                    "Could not save response node: " + details.statusText);
            });
    };
}])


.controller('StatisticsCtrl', [
        '$scope', 'QuestionNode', 'routeData', 'Editor', 'questionAuthz',
        '$location', 'Notifications', 'Current', 'format', 'Structure',
        'layout', 'Arrays', 'ResponseNode', 'Statistics', 'Assessment',
        function($scope, QuestionNode, routeData, Editor, authz,
                 $location, Notifications, current, format, Structure,
                 layout, Arrays, ResponseNode, Statistics, Assessment) {

    var boxQuartiles = function(d) {
        return [
            d.quartile[0],
            d.current,
            d.quartile[1],
            d.quartile[2]
        ];
    };

    // Inspired by http://informationandvisualization.de/blog/box-plot
    d3.box = function() {
        var width = 1,
            height = 1,
            duration = 0,
            domain = null,
            value = Number,
            // whiskers = boxWhiskers,
            quartiles = boxQuartiles,
            detailChart = detailChart,
            tickFormat = null;

        function wrap(text, width) {
          text.each(function() {
            var text = d3.select(this),
                words = text.text().split(/\s+/).reverse(),
                word,
                line = [],
                lineNumber = 0,
                lineHeight = 1.1, // ems
                y = text.attr("y"),
                dy = parseFloat(text.attr("dy")),
                tspan = text.text(null).append("tspan").attr("x", 0).attr("y", y).attr("dy", dy + "em");
                console.log(text);
            while (word = words.pop()) {
              line.push(word);
              tspan.text(line.join(" "));
              if (tspan.node().getComputedTextLength() > width) {
                line.pop();
                tspan.text(line.join(" "));
                line = [word];
                tspan = text.append("tspan").attr("x", 0).attr("y", y).attr("dy", ++lineNumber * lineHeight + dy + "em").text(word);
              }
            }
          });
        }

        function type(d) {
          d.value = +d.value;
          return d;
        }

      // For each small multiple…
        function box(g) {
            g.each(function(d, i) {
                console.log(d);
                var g = d3.select(this),
                    n = d.length,
                    min = d.min,
                    max = d.max;

                // Compute quartiles. Must return exactly 3 elements.
                var quartileData = d.quartiles = quartiles(d);

                // Compute whiskers. Must return exactly 2 elements, or null.
                var whiskerData = [d.min, d.max];

                // Compute outliers. If no whiskers are specified, all data are "outliers".
                // We compute the outliers as indices, so that we can join across transitions!
                var outlierIndices = d3.range(n);

                // Compute the new x-scale.
                var x1 = d3.scale.linear()
                  .domain(domain && domain.call(this, d, i) || [min, max])
                  .range([height - 20, 0]);

                // Retrieve the old x-scale, if this is an update.
                var x0 = this.__chart__ || d3.scale.linear()
                  .domain([0, Infinity])
                  .range(x1.range());

                // Stash the new scale.
                this.__chart__ = x1;

                // Note: the box, median, and box tick elements are fixed in number,
                // so we only have to handle enter and update. In contrast, the outliers
                // and other elements are variable, so we need to exit them! Variable
                // elements also fade in and out.

                // Update center line: the vertical line spanning the whiskers.
                var center = g.selectAll("line.center")
                    .data([whiskerData]);

                center.enter().insert("line", "rect")
                    .attr("class", "center")
                    .attr("x1", width / 2)
                    .attr("y1", function(d) { return x0(d[0]); })
                    .attr("x2", width / 2)
                    .attr("y2", function(d) { return x0(d[1]); })
                    .style("opacity", 1e-6)
                .transition()
                    .duration(duration)
                    .style("opacity", 1)
                    .attr("y1", function(d) { return x1(d[0]); })
                    .attr("y2", function(d) { return x1(d[1]); });

                center.transition()
                    .duration(duration)
                    .style("opacity", 1)
                    .attr("y1", function(d) { return x1(d[0]); })
                    .attr("y2", function(d) { return x1(d[1]); });

                center.exit().transition()
                    .duration(duration)
                    .style("opacity", 1e-6)
                    .attr("y1", function(d) { return x1(d[0]); })
                    .attr("y2", function(d) { return x1(d[1]); })
                    .remove();

                // Update innerquartile box.
                var box = g.selectAll("rect.box")
                    .data([quartileData]);

                box.enter().append("rect")
                    .attr("class", "box")
                    .attr("x", 0)
                    .attr("y", function(d) { return x0(d[3]); })
                    .attr("width", width)
                    .attr("height", function(d) { return x0(d[0]) - x0(d[3]); })
                    .transition()
                        .duration(duration)
                        .attr("y", function(d) { return x1(d[3]); })
                        .attr("height", function(d) { return x1(d[0]) - x1(d[3]); });

                box.transition()
                    .duration(duration)
                    .attr("y", function(d) { return x1(d[3]); })
                    .attr("height", function(d) { return x1(d[0]) - x1(d[3]); });

                // Update median line.
                var medianLine = g.selectAll("line.median")
                    .data([quartileData[2]]);

                medianLine.enter().append("line")
                    .attr("class", "median")
                    .attr("x1", 0)
                    .attr("y1", x0)
                    .attr("x2", width)
                    .attr("y2", x0)
                    .transition()
                        .duration(duration)
                        .attr("y1", x1)
                        .attr("y2", x1);

                medianLine.transition()
                    .duration(duration)
                    .attr("y1", x1)
                    .attr("y2", x1);

                // Update current line.
                var currentLine = g.selectAll("line.current")
                    .data([quartileData[1]]);

                currentLine.enter().append("line")
                    .attr("class", "current")
                    .attr("x1", 0)
                    .attr("y1", x0)
                    .attr("x2", width)
                    .attr("y2", x0)
                    .transition()
                        .duration(duration)
                        .attr("y1", x1)
                        .attr("y2", x1);

                currentLine.transition()
                    .duration(duration)
                    .attr("y1", x1)
                    .attr("y2", x1);

                // Update current text
                var currentTick = g.selectAll("current.text")
                    .data([quartileData[1]]);

                currentTick.enter().append("text")
                    .attr("class", "current_text")
                    .attr("dy", ".3em")
                    .attr("dx", 5)
                    .attr("x", width)
                    .attr("y", x0)
                    .attr("text-anchor", "start")
                    .text(x1.tickFormat(8))
                    .style("opacity", 1e-6)
                    .transition()
                        .duration(duration)
                        .attr("y", x1)
                        .style("opacity", 1);

                currentTick.transition()
                    .duration(duration)
                    .text(x1.tickFormat(8))
                    .attr("y", x1)
                    .style("opacity", 1);

                currentTick.exit().transition()
                    .duration(duration)
                    .attr("y", x1)
                    .style("opacity", 1e-6)
                    .remove();




                // Update whiskers.
                var whisker = g.selectAll("line.whisker")
                    .data(whiskerData || []);

                whisker.enter().insert("line", "circle, text")
                    .attr("class", "whisker")
                    .attr("x1", 0)
                    .attr("y1", x0)
                    .attr("x2", width)
                    .attr("y2", x0)
                    .style("opacity", 1e-6)
                    .transition()
                    .duration(duration)
                    .attr("y1", x1)
                    .attr("y2", x1)
                    .style("opacity", 1);

                whisker.transition()
                    .duration(duration)
                    .attr("y1", x1)
                    .attr("y2", x1)
                    .style("opacity", 1);

                whisker.exit().transition()
                    .duration(duration)
                    .attr("y1", x1)
                    .attr("y2", x1)
                    .style("opacity", 1e-6)
                    .remove();

                // Compute the tick format.
                var format = tickFormat || x1.tickFormat(8);

                // Update box ticks.
                // var boxTick = g.selectAll("text.box")
                //     .data(quartileData);

                // boxTick.enter().append("text")
                //     .attr("class", "box")
                //     .attr("dy", ".3em")
                //     .attr("dx", function(d, i) { return i & 1 ? 6 : -6 })
                //     .attr("x", function(d, i) { return i & 1 ? width : 0 })
                //     .attr("y", x0)
                //     .attr("text-anchor", function(d, i) { return i & 1 ? "start" : "end"; })
                //     // .text(format)
                //   .transition()
                //     .duration(duration)
                //     .attr("y", x1);

                // boxTick.transition()
                //     .duration(duration)
                //     // .text(format)
                //     .attr("y", x1);

                // Update whisker ticks. These are handled separately from the box
                // ticks because they may or may not exist, and we want don't want
                // to join box ticks pre-transition with whisker ticks post-.
                var whiskerTick = g.selectAll("text.whisker")
                    .data(whiskerData || []);

                whiskerTick.enter().append("text")
                    .attr("class", "whisker")
                    .attr("dy", ".3em")
                    .attr("dx", -25)
                    .attr("x", width)
                    .attr("y", x0)
                    .attr("text-anchor", "end")
                    .text(format)
                    .style("opacity", 1e-6)
                    .transition()
                        .duration(duration)
                        .attr("y", x1)
                        .style("opacity", 1);

                whiskerTick.transition()
                    .duration(duration)
                    .text(format)
                    .attr("y", x1)
                    .style("opacity", 1);

                whiskerTick.exit().transition()
                    .duration(duration)
                    .attr("y", x1)
                    .style("opacity", 1e-6)
                    .remove();

                var title = g.selectAll("title.textbox")
                    .data([d]);

                title.enter().append("text")
                    .attr("x", 0)
                    .attr("y", x0(0) - 30)
                    .attr("dy", 5)
                    .attr("text-anchor", "middle")
                    .text(function(d) { return d.title; })
                    .call(wrap, 100)
            });
            d3.timer.flush();
        }

        box.width = function(x) {
            if (!arguments.length) return width;
                width = x;
            return box;
        };

        box.height = function(x) {
            if (!arguments.length) return height;
                height = x;
            return box;
        };

        box.tickFormat = function(x) {
            if (!arguments.length) return tickFormat;
                tickFormat = x;
            return box;
        };

        box.duration = function(x) {
            if (!arguments.length) return duration;
                duration = x;
            return box;
        };

        box.domain = function(x) {
            if (!arguments.length) return domain;
                domain = x == null ? x : d3.functor(x);
            return box;
        };

        box.value = function(x) {
            if (!arguments.length) return value;
                value = x;
            return box;
        };

        box.whiskers = function() {
            return box;
        };

        box.quartiles = function(x) {
            if (!arguments.length) return quartiles;
                quartiles = x;
            return box;
        };

        box.detailChart = function(x) {
            if (!arguments.length) return detailChart;
                detailChart = x;
            return box;
        };

        return box;
    };


    // Start ucustom logic here
    $scope.assessment = routeData.assessment;
    $scope.qnode = routeData.qnode;
    $scope.compare = function(assessment) {
        ResponseNode.query({
            assessmentId: assessment.id,
            parentId: null,
            hierarchyId: null,
            root: ''
        }).$promise.then(function(rnodes){
            var svg_current = d3.select("#chart").selectAll("svg");
            var data = [];
            angular.forEach(svg_current[0], function(svg_node, index) {
                var existing_data = svg_node.__data__;
                var nodes = rnodes.filter(function(n) {
                    if(n.qnode.id == existing_data.id) {
                        return n;
                    }
                });
                var node = nodes[0];
                if (node) {
                    var d = {};
                    d['id'] = node.qnode.id;
                    d['current'] = node.score;
                    d['max'] = existing_data.max;
                    d['min'] = existing_data.min;
                    d['quartile'] = existing_data.quartile;
                    // d['name'] = "F" + (index + 1);
                    data.push(d);                    
                }
                data.push(existing_data);
            })
            d3.select("#chart").selectAll("svg").remove();
            console.log(data);
            svg.data(data)
                        .enter().append("svg")
                            .attr("class", "box")
                            .attr("width", width + margin.left + margin.right)
                            .attr("height", height + margin.bottom + margin.top)
                            .on("click", function(d) {
                                detailChart(d.id);
                            })
                        .append("g")
                            .attr("transform", "translate(" + margin.left + "," + margin.top + ")")
                            .call(chart.duration(1000));

        });
    }

    if ($scope.assessment) {
        $scope.rnode = ResponseNode.query({
            assessmentId: $scope.assessment.id,
            parentId: $scope.qnode ? $scope.qnode.id : null,
            hierarchyId: $scope.hierarchy ? $scope.hierarchy.id : null,
            root: $scope.qnode ? null : ''
        });
    }

    var margin = {top: 10, right: 50, bottom: 20, left: 50},
        width = 120 - margin.left - margin.right,
        height = 600 - margin.top - margin.bottom;

    var detailChart = function(qnode) {
        $scope.qnode = {'id': qnode};
        $scope.rnode = ResponseNode.query({
            assessmentId: $scope.assessment.id,
            parentId: $scope.qnode ? $scope.qnode.id : null,
            hierarchyId: $scope.hierarchy ? $scope.hierarchy.id : null,
            root: $scope.qnode ? null : ''
        });
    };

    var chart = d3.box()
        .whiskers()
        .width(width)
        .height(height);

    var svg = d3.select("#chart").selectAll("svg");


    $scope.$watch('rnode', function(rnode) {
        rnode.$promise.then(function success(rnodes) {
            Statistics.get({id: $scope.assessment.survey.id, parent_id: $scope.qnode ? $scope.qnode.id:null}).$promise.then(function(stats) {
                var data = [];
                angular.forEach(rnodes, function(node, index) {
                    var stat = stats.filter(function(s) {
                        if(s.qid == node.qnode.id) {
                            return s;
                        }
                    });
                    stat = stat[0];
                    var d = {};
                    d['id'] = node.qnode.id;
                    d['current'] = node.score;
                    d['max'] = stat.max;
                    d['min'] = stat.min;
                    d['quartile'] = stat.quartile;
                    d['title'] = stat.title;
                    data.push(d);
                });

    
                if (data.length > 0) {
                    d3.select("#chart").selectAll("svg").remove();

                    svg.data(data)
                        .enter().append("svg")
                            .attr("class", "box")
                            .attr("width", width + margin.left + margin.right)
                            .attr("height", height + margin.bottom + margin.top)
                            .on("click", function(d) {
                                detailChart(d.id);
                            })
                        .append("g")
                            .attr("transform", "translate(" + margin.left + "," + margin.top + ")")
                            .call(chart.duration(1000));

                }

            });
            Assessment.query({'trackingId':$scope.assessment.survey.trackingId}).$promise.then(function(oldAssessments) {
                $scope.oldAssessments = oldAssessments.filter(function(assessment) {
                    return $scope.assessment.id != assessment.id;
                });
            });
        });
    });
}])


.controller('QnodeChildren', ['$scope', 'bind', 'Editor', 'QuestionNode',
        'ResponseNode', 'Notifications',
        function($scope, bind, Editor, QuestionNode, ResponseNode,
            Notifications) {

    bind($scope, 'children', $scope, 'model', true);

    $scope.edit = Editor('model', $scope, {}, QuestionNode);
    $scope.$on('EditSaved', function(event, model) {
        event.stopPropagation();
    });

    $scope.dragOpts = {
        axis: 'y',
        handle: '.grab-handle'
    };

    if ($scope.assessment) {
        $scope.query = 'assessment=' + $scope.assessment.id;
    } else if ($scope.hierarchy) {
        $scope.query = 'survey=' + $scope.survey.id;
        $scope.query += '&hierarchy=' + $scope.hierarchy.id;
        $scope.edit.params = {
            surveyId: $scope.survey.id,
            hierarchyId: $scope.hierarchy.id,
            root: ''
        }
    } else {
        $scope.query = 'survey=' + $scope.survey.id;
        $scope.edit.params.parentId = $scope.qnode.id;
        $scope.edit.params = {
            surveyId: $scope.survey.id,
            parentId: $scope.qnode.id
        }
    }

    $scope.$watchGroup(['hierarchy', 'structure'], function(vars) {
        var level;
        if ($scope.assessment && !$scope.qnode)
            level = $scope.assessment.hierarchy.structure.levels[0];
        else if ($scope.hierarchy)
            level = $scope.hierarchy.structure.levels[0];
        else
            level = $scope.nextLevel;
        $scope.level = level;
    });

    if ($scope.assessment) {
        // Get the responses that are associated with this qnode and assessment.
        ResponseNode.query({
            assessmentId: $scope.assessment.id,
            parentId: $scope.qnode ? $scope.qnode.id : null,
            hierarchyId: $scope.hierarchy ? $scope.hierarchy.id : null,
            root: $scope.qnode ? null : ''
        }).$promise.then(
            function success(rnodes) {
                var rmap = {};
                for (var i = 0; i < rnodes.length; i++) {
                    var rnode = rnodes[i];
                    var nm = rnode.qnode.nMeasures;
                    rmap[rnode.qnode.id] = {
                        score: rnode.score,
                        notRelevant: rnode.notRelevant,
                        progressItems: [
                            {
                                name: 'Final',
                                value: rnode.nSubmitted,
                                fraction: rnode.nSubmitted / nm
                            },
                            {
                                name: 'Reviewed',
                                value: rnode.nReviewed,
                                fraction: rnode.nReviewed / nm
                            },
                            {
                                name: 'Approved',
                                value: rnode.nApproved,
                                fraction: rnode.nApproved / nm
                            },
                        ]
                    };
                }
                $scope.rnodeMap = rmap;
            },
            function failure(details) {
                Notifications.set('edit', 'error',
                    "Could not get aggregate scores: " +
                    details.statusText);
            }
        );
    }
    var dummyStats = {
        score: 0,
        notRelevant: false,
        progressItems: [
            {
                name: 'Final',
                value: 0,
                fraction: 0
            },
            {
                name: 'Reviewed',
                value: 0,
                fraction: 0
            },
            {
                name: 'Approved',
                value: 0,
                fraction: 0
            },
        ]
    };
    $scope.getStats = function(qnodeId) {
        if ($scope.rnodeMap && $scope.rnodeMap[qnodeId])
            return $scope.rnodeMap[qnodeId];
        else
            return dummyStats;
    };
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

    $scope.level = $scope.structure.hierarchy.structure.measure;

    if ($scope.assessment) {
        // Get the responses that are associated with this qnode and assessment.
        Response.query({
            assessmentId: $scope.assessment.id,
            qnodeId: $scope.qnode.id
        }).$promise.then(
            function success(responses) {
                var rmap = {};
                for (var i = 0; i < responses.length; i++) {
                    var r = responses[i];
                    var nApproved = r.approval == 'approved' ? 1 : 0;
                    var nReviewed = r.approval == 'reviewed' ? 1 : nApproved;
                    var nSubmitted = r.approval == 'final' ? 1 : nReviewed;
                    rmap[r.measure.id] = {
                        score: r.score,
                        notRelevant: r.notRelevant,
                        progressItems: [
                            {
                                name: 'Final',
                                value: nSubmitted,
                                fraction: nSubmitted
                            },
                            {
                                name: 'Reviewed',
                                value: nReviewed,
                                fraction: nReviewed
                            },
                            {
                                name: 'Approved',
                                value: nApproved,
                                fraction: nApproved
                            },
                        ]
                    };
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
    var dummyStats = {
        score: 0,
        notRelevant: false,
        progressItems: [
            {
                name: 'Final',
                value: 0,
                fraction: 0
            },
            {
                name: 'Reviewed',
                value: 0,
                fraction: 0
            },
            {
                name: 'Approved',
                value: 0,
                fraction: 0
            },
        ]
    };
    $scope.getStats = function(measureId) {
        if ($scope.responseMap && $scope.responseMap[measureId])
            return $scope.responseMap[measureId];
        else
            return dummyStats;
    };
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
            function success(response) {
                $scope.$broadcast('response-saved');
                Notifications.set('edit', 'success', "Saved", 5000);
            },
            function failure(details) {
                Notifications.set('edit', 'error',
                    "Could not save response: " + details.statusText);
            });
    };
    $scope.toggleNotRelvant = function() {
        var oldValue = $scope.response.notRelevant;
        $scope.response.notRelevant = !oldValue;
        $scope.response.$save().then(
            function success() {
                Notifications.set('edit', 'success', "Saved", 5000);
            },
            function failure(details) {
                if (details.status == 403) {
                    Notifications.set('edit', 'info',
                        "Not saved yet: " + details.statusText);
                } else {
                    $scope.response.notRelevant = oldValue;
                    Notifications.set('edit', 'error',
                        "Could not save response: " + details.statusText);
                }
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
    $scope.setResponse = function(response) {
        $scope.response = response;
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

        $scope.checkRole = authz(current, $scope.survey, $scope.assessment);
        $scope.editable = ($scope.survey.isEditable &&
            !$scope.assessment && $scope.checkRole('measure_edit'));
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

    $scope.getAssessmentUrl = function(assessment) {
        if (assessment) {
            return format('/measure/{}?assessment={}&parent={}',
                $scope.measure.id, assessment.id,
                $scope.parent && $scope.parent.id || '');
        } else {
            return format('/measure/{}?survey={}&parent={}',
                $scope.measure.id, $scope.survey.id,
                $scope.parent && $scope.parent.id || '');
        }
    };
}])


.controller('ResponseAttachmentCtrl', [
        '$scope', 'Attachment', '$http', '$cookies', 'Notifications',
        function($scope, Attachment, $http, $cookies, Notifications) {

    $scope.attachments = null;

    var headers = {};
    var xsrfName = $http.defaults.xsrfHeaderName;
    headers[xsrfName] = $cookies.get($http.defaults.xsrfCookieName);
    $scope.externals = [];
    $scope.addExternal = function() {
        $scope.externals.push({"url": ""});
    }
    $scope.toggleFileDrop = function() {
        $scope.showFileDrop = !$scope.showFileDrop;
    };

    $scope.deleteExternal = function(index) {
        if (index > -1) {
            $scope.externals.splice(index, 1);
        }
    }

    var config = {
        url: '/',
        maxFilesize: 10,
        paramName: "file",
        headers: headers,
        // uploadMultiple: true,
        autoProcessQueue: false
    };

    Dropzone.autoDiscover = false;
    var dropzone = new Dropzone("#dropzone", config);

    $scope.save = function() {
        $scope.upload();
        if ($scope.externals.length > 0) {
            Attachment.saveExternals({
                assessmentId: $scope.assessment.id,
                measureId: $scope.measure.id,
                externals: $scope.externals
            }).$promise.then(
                function success(attachments) {
                    $scope.attachments = attachments;
                    $scope.externals = [];
                },
                function failure(details) {
                    if ($scope.attachments) {
                        Notifications.set('attach', 'error',
                            "Failed to add attachments: " +
                            details.statusText);
                    }
                }
            );
        }
    }
    $scope.upload = function() {
        $scope.hasError = false;
        if (dropzone.files.length > 0) {
            dropzone.options.url = '/assessment/' + $scope.assessment.id +
                '/measure/' + $scope.measure.id + '/attachment.json';
            dropzone.options.autoProcessQueue = true;
            dropzone.processQueue();
        }
    };
    $scope.cancelNewAttachments = function() {
        dropzone.removeAllFiles();
        $scope.showFileDrop = false;
        $scope.externals = [];
    };

    $scope.$on('response-saved', $scope.save);

    $scope.refreshAttachments = function() {
        Attachment.query({
            assessmentId: $scope.assessment.id,
            measureId: $scope.measure.id
        }).$promise.then(
            function success(attachments) {
                $scope.attachments = attachments;
            },
            function failure(details) {
                if ($scope.attachments) {
                    Notifications.set('attach', 'error',
                        "Failed to refresh attachment list: " +
                        details.statusText);
                }
            }
        );
    };
    $scope.refreshAttachments();
    $scope.safeUrl = function(url) {
        return !! /^(https?|ftp):\/\//.exec(url);
    };

    dropzone.on("queuecomplete", function() {

        $scope.showFileDrop = false;
        dropzone.removeAllFiles();
        $scope.refreshAttachments();

        if ($scope.hasError) {
            Notifications.set('attach', 'error', "Not all attachments are saved", 5000);
        } else {
            Notifications.set('attach', 'info', "Attachments saved", 5000);
        }
    });

    dropzone.on("error", function(file, details, request) {
        var error;
        if (request) {
            error = "Import failed: " + request.statusText;
        } else {
            error = details;
        }
        console.log('error');
        dropzone.options.autoProcessQueue = false;
        dropzone.removeAllFiles();
        Notifications.set('attach', 'error', error);
        $scope.hasError = true;
    });
    $scope.deleteAttachment = function(attachment) {
        var isExternal = attachment.url;
        Attachment.remove({id: attachment.id}).$promise.then(
            function success() {
                var message;
                if (!isExternal) {
                    message = "The attachment was removed, but it can not be " +
                              "deleted from the database.";
                } else {
                    message = "Link removed.";
                }
                Notifications.set('attach', 'success', message, 5000);
                $scope.refreshAttachments();
            },
            function failure(details) {
                Notifications.set('attach', 'error',
                    "Could not delete attachment: " + details.statusText);
            }
        );
    };
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


/**
 * Drop-down menu to navigate to old versions of an entity.
 */
.controller('ResponseHistory', ['$scope', '$location', 'Response',
        'Notifications',
        function($scope, $location, Response, Notifications) {
    $scope.toggled = function(open) {
        if (open) {
            $scope.search = {
                assessmentId: $scope.assessment.id,
                measureId: $scope.measure.id,
                page: 0,
                pageSize: 10
            };
        } else {
            $scope.search = null;
        }
    };

    $scope.search = null;

    $scope.$watch('search', function(search) {
        if (!search)
            return;
        $scope.loading = true;
        Response.history(search).$promise.then(
            function success(versions) {
                $scope.versions = versions;
                $scope.loading = false;
            },
            function failure(details) {
                $scope.loading = false;
            }
        );
    }, true);

    $scope.nextPage = function($event) {
        if ($scope.search.page > 0)
            $scope.search.page--;
        $event.preventDefault();
        $event.stopPropagation();
    };
    $scope.prevPage = function($event) {
        if ($scope.versions.length >= $scope.search.pageSize)
            $scope.search.page++;
        $event.preventDefault();
        $event.stopPropagation();
    };

    $scope.navigate = function(version) {
        var query = {
            measureId: $scope.measure.id,
            assessmentId: $scope.assessment.id,
            version: version.version
        };
        Response.get(query).$promise.then(
            function success(response) {
                $scope.setResponse(response);
            },
            function failure(details) {
                Notifications.set('edit', 'error',
                    "Could not get response: " + details.statusText);
            }
        );
    };
    $scope.isActive = function(version) {
        return version.version == $scope.response.version;
    };
}])


.directive('approval', [function() {
    return {
        restrict: 'E',
        scope: {
            model: '='
        },
        template: '<i class="boxed" ng-class="cls" title="{{model}}">' +
                    '{{initial}}</i>',
        replace: true,
        controller: ['$scope', function($scope) {
            $scope.$watch('model', function(approval) {
                $scope.initial = approval[0].toUpperCase();
                switch (approval) {
                case 'draft':
                    $scope.initial = 'D';
                    $scope.cls = 'aq-0';
                    break;
                case 'final':
                    $scope.initial = 'F';
                    $scope.cls = 'aq-1';
                    break;
                case 'reviewed':
                    $scope.initial = 'R';
                    $scope.cls = 'aq-2';
                    break;
                case 'approved':
                    $scope.initial = 'A';
                    $scope.cls = 'aq-3';
                    break;
                }
            });
        }]
    };
}])


;
