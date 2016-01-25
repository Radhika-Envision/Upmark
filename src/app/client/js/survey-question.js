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


.factory('QuestionNode', ['$resource', 'paged', function($resource, paged) {
    return $resource('/qnode/:id.json', {id: '@id'}, {
        get: { method: 'GET', cache: false },
        create: { method: 'POST' },
        save: { method: 'PUT' },
        query: {
            method: 'GET', isArray: true, cache: false,
            interceptor: {response: paged}
        },
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


.factory('Diff', ['$resource', function($resource) {
    return $resource('/diff.json', {}, {
        get: { method: 'GET', isArray: false, cache: false }
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

    $scope.search = {
        deleted: false
    };
    $scope.$watch('search.deleted', function() {
        if (!$scope.survey.id)
            return;
        Hierarchy.query({
            surveyId: $scope.survey.id,
            deleted: $scope.search.deleted
        }, function success(hierarchies) {
            $scope.hierarchies = hierarchies
        }, function failure(details) {
                Notifications.set('edit', 'error',
                    "Could not get list of surveys: " + details.statusText);
        });
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
        scope: {
            assessment: '=assessmentSelect',
            org: '=',
            survey: '=',
            track: '@',
            hierarchy: '=',
            formatUrl: '=',
            disallowNone: '='
        },
        controller: ['$scope', 'Current', 'Assessment', 'Organisation',
                '$location', 'format', 'Notifications', 'PurchasedSurvey',
                'Structure', 'questionAuthz', 'Enqueue',
                function($scope, current, Assessment, Organisation,
                         $location, format, Notifications, PurchasedSurvey,
                         Structure, authz, Enqueue) {

            $scope.aSearch = {
                organisation: null,
                historical: false
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

            $scope.$watch('hierarchy', function(hierarchy) {
                $scope.search.hierarchyId = hierarchy ? hierarchy.id : null;
            });

            $scope.$watchGroup(['survey', 'aSearch.historical'], function(vars) {
                var survey = vars[0],
                    historical = vars[1];

                if (historical) {
                    $scope.search.trackingId = survey ? survey.trackingId : null;
                    $scope.search.surveyId = null;
                } else {
                    $scope.search.trackingId = null;
                    $scope.search.surveyId = survey ? survey.id : null;
                }
            });
            $scope.$watch('track', function(track) {
                $scope.aSearch.historical = track != null;
                $scope.showEdit = track == null;
            });

            $scope.historical = false;
            $scope.search = {
                term: "",
                orgId: null,
                hierarchyId: null,
                surveyId: null,
                trackingId: null,
                deleted: false,
                page: 0,
                pageSize: 5
            };
            $scope.applySearch = Enqueue(function() {
                Assessment.query($scope.search).$promise.then(
                    function success(assessments) {
                        $scope.assessments = assessments;
                    },
                    function failure(details) {
                        Notifications.set('survey', 'error',
                            "Could not get submission list: " + details.statusText);
                    }
                );
            }, 100);
            $scope.$watch('search', $scope.applySearch, true);

            $scope.$watchGroup(['survey', 'search.orgId', 'hierarchy', 'track'],
                    function(vars) {

                var survey = vars[0];
                var orgId = vars[1];
                var hierarchy = vars[2];
                var track = vars[3];

                if (!survey || !orgId || !hierarchy || track != null) {
                    $scope.purchasedSurvey = null;
                    return;
                }

                PurchasedSurvey.head({
                    surveyId: survey.id,
                    id: orgId,
                    hid: hierarchy.id
                }, null, function success(purchasedSurvey) {
                    $scope.purchasedSurvey = purchasedSurvey;
                }, function failure(details) {
                    if (details.status == 404) {
                        $scope.purchasedSurvey = null;
                        return;
                    }
                    Notifications.set('survey', 'error',
                        "Could not get purchase status: " + details.statusText);
                });
            });

            // Allow parent controller to specify a special URL formatter - this
            // is so one can switch between assessments without losing one's
            // place in the hierarchy.
            $scope.getAssessmentUrl = function(assessment) {
                if ($scope.formatUrl)
                    return $scope.formatUrl(assessment)

                if (assessment) {
                    return format('/assessment/{}', assessment.id);
                } else {
                    return format('/hierarchy/{}?survey={}',
                        $scope.hierarchy.id, $scope.survey.id);
                }
            };

            $scope.checkRole = authz(current, $scope.survey);
        }]
    }
}])


.controller('SurveyListCtrl', ['$scope', 'questionAuthz', 'Survey', 'Current',
        'layout',
        function($scope, authz, Survey, current, layout) {

    $scope.layout = layout;
    $scope.checkRole = authz(current, null);

    $scope.search = {
        term: "",
        editable: $scope.checkRole('survey_edit'),
        deleted: false,
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
        title: "AMCV Import",
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
        controller: ['$scope', '$location', 'format', 'Structure',
                    function($scope, $location, format, Structure) {

            $scope.$watch('entity', function(entity) {
                $scope.structure = Structure($scope.entity);
            });

            $scope.toggled = function(open) {
                if (open) {
                    $scope.surveys = $scope.service.history({
                        id: $scope.entity.id,
                        deleted: false
                    });
                }
            };

            $scope.navigate = function(survey) {
                if ($scope.entity == $scope.structure.survey)
                    $location.url('/survey/' + survey.id);
                else
                    $location.search('survey', survey.id);
            };
            $scope.isActive = function(survey) {
                if ($scope.entity == $scope.structure.survey)
                    return $location.url().indexOf('/survey/' + survey.id) >= 0;
                else
                    return $location.search().survey == survey.id;
            };

            $scope.compare = function(survey, event) {
                var s1, s2;
                if (survey.created < $scope.structure.survey.created) {
                    s1 = survey;
                    s2 = $scope.structure.survey;
                } else {
                    s1 = $scope.structure.survey;
                    s2 = survey;
                }
                var url = format(
                    '/diff/{}/{}/{}?ignoreTags=list+index',
                    s1.id,
                    s2.id,
                    $scope.structure.hierarchy.id);
                $location.url(url);
                event.preventDefault();
                event.stopPropagation();
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
            var lineage = "";
            // Qnodes and measures
            for (var i = 2; i <= qnodeMaxIndex; i++) {
                entity = stack[i];
                var level = structure.levels[i - 2];
                if (entity.seq != null)
                    lineage += "" + (entity.seq + 1) + ".";
                else
                    lineage += "-.";
                hstack.push({
                    path: 'qnode',
                    title: level.title,
                    label: level.label,
                    entity: entity,
                    level: i - 2,
                    lineage: lineage
                });
                qnodes.push(entity);
            }

            if (measure) {
                if (measure.seq != null)
                    lineage += "" + (measure.seq + 1) + ".";
                else
                    lineage += "-.";
                hstack.push({
                    path: 'measure',
                    title: structure.measure.title,
                    label: structure.measure.label,
                    entity: measure,
                    level: 'm',
                    lineage: lineage
                });
            }
        }

        var deletedItem = null;
        for (var i = 0; i < hstack.length; i++) {
            var item = hstack[i];
            if (item.entity.deleted)
                deletedItem = item;
        }

        return {
            survey: survey,
            hierarchy: hierarchy,
            assessment: assessment,
            qnodes: qnodes,
            measure: measure,
            hstack: hstack,
            deletedItem: deletedItem
        };
    };
})


.directive('questionHeader', [function() {
    return {
        restrict: 'E',
        scope: {
            entity: '=',
            assessment: '=',
            getUrl: '='
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

                if ($scope.getUrl) {
                    var url = $scope.getUrl(item, key);
                    if (url)
                        return url;
                }

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
                if (item.path == 'measure' && item.entity.parent
                        && !$scope.assessment) {
                    query.push('parent=' + item.entity.parent.id);
                }
                url = path + '?' + query.join('&');

                return url;
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
    $scope.org = routeData.org;
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
    $scope.$watchGroup(['hierarchy', 'hierarchy.deleted'], function() {
        $scope.structure = Structure($scope.hierarchy);
        $scope.editable = ($scope.survey.isEditable &&
            !$scope.structure.deletedItem &&
            $scope.checkRole('survey_node_edit'));
    });

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
        'layout', 'Arrays', 'ResponseNode', 'Enqueue', '$timeout', '$route',
        'dimmer',
        function($scope, QuestionNode, routeData, Editor, authz,
                 $location, Notifications, current, format, Structure,
                 layout, Arrays, ResponseNode, Enqueue, $timeout, $route,
                 dimmer) {

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

    $scope.$watchGroup(['qnode', 'qnode.deleted'], function() {
        $scope.structure = Structure($scope.qnode, $scope.assessment);
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

        $scope.checkRole = authz(current, $scope.survey, $scope.assessment);
        $scope.editable = ($scope.survey.isEditable &&
            !$scope.structure.deletedItem &&
            !$scope.assessment &&
            $scope.checkRole('survey_node_edit'));
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

    // Used to get history
    $scope.QuestionNode = QuestionNode;

    if ($scope.assessment) {
        $scope.rnode = ResponseNode.get({
            assessmentId: $scope.assessment.id,
            qnodeId: $scope.qnode.id
        });

        var disableUpdate = false;
        var importanceToView = function() {
            // When saving, the server may choose to change these values.
            // Temporarily disable updates to prevent a save-loop.
            var rnode = $scope.rnode;
            $scope.stats.importance = rnode.importance || rnode.maxImportance;
            $scope.stats.urgency = rnode.urgency || rnode.maxUrgency;

            disableUpdate = true;
            $timeout(function() {
                disableUpdate = false;
            });
        };

        $scope.updateStats = function(rnode) {
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
                ],
                approval: rnode.nApproved >= $scope.qnode.nMeasures ?
                        'approved' :
                    rnode.nReviewed >= $scope.qnode.nMeasures ?
                        'reviewed' :
                    rnode.nSubmitted >= $scope.qnode.nMeasures ?
                        'final' :
                        'draft',
                promote: 'BOTH',
                missing: 'CREATE',
            };
            importanceToView();
        };

        $scope.rnode.$promise.then(
            function success(rnode) {
                $scope.rnodeDup = angular.copy(rnode);
                $scope.updateStats(rnode);
            },
            function failure(details) {
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
            }
        );

        $scope.saveRnode = Enqueue(function() {
            $scope.rnode.$save().then(
                function success(rnode) {
                    $scope.rnodeDup = angular.copy(rnode);
                    $scope.updateStats(rnode);
                    Notifications.set('edit', 'success', "Saved", 5000);
                },
                function failure(details) {
                    angular.copy($scope.rnodeDup, $scope.rnode)
                    Notifications.set('edit', 'error',
                        "Could not save submission category: " + details.statusText);
                });
        }, 1500);
        $scope.$watch('stats.importance', function(v, vOld) {
            if (disableUpdate || vOld === undefined)
                return;
            $scope.rnode.importance = v;
        });
        $scope.$watch('stats.urgency', function(v, vOld) {
            if (disableUpdate || vOld === undefined)
                return;
            $scope.rnode.urgency = v;
        });
        $scope.$watchGroup(
                ['rnode.notRelevant', 'rnode.importance', 'rnode.urgency'],
                function(vals, oldVals) {
            if (oldVals.every(function(v) { return v === undefined }))
                return;
            if (disableUpdate)
                return;
            $scope.saveRnode();
        });

        $scope.dim = dimmer.toggler($scope);
        $scope.showBulkApproval = false;
        $scope.toggleBulk = function() {
            $scope.showBulkApproval = !$scope.showBulkApproval;
            $scope.dim($scope.showBulkApproval);
        };

        $scope.promotionOptions = [{
            name: 'BOTH',
            desc: "Promote and demote existing responses to match chosen state",
        }, {
            name: 'PROMOTE',
            desc: "Only promote existing responses",
        }, {
            name: 'DEMOTE',
            desc: "Only demote existing responses",
        },];

        $scope.missingOptions = [{
            name: 'CREATE',
            desc: "Create responses where they are missing and mark as Not Relevant",
        }, {
            name: 'IGNORE',
            desc: "Don't create missing responses",
        },];

        $scope.setState = function(approval) {
            var promote;
            if ($scope.stats.promote == 'BOTH')
                promote = ['PROMOTE', 'DEMOTE'];
            else if ($scope.stats.promote == 'PROMOTE')
                promote = ['PROMOTE'];
            else
                promote = ['DEMOTE'];
            $scope.rnode.$save({
                    approval: approval,
                    promote: promote,
                    missing: $scope.stats.missing,
                },
                function success(rnode, getResponseHeaders) {
                    var message = "Saved";
                    if (getResponseHeaders('Operation-Details'))
                        message += ": " + getResponseHeaders('Operation-Details');
                    Notifications.set('edit', 'success', message, 5000);
                    // Need to actually reload the route because the list of
                    // children and measures will have changed too.
                    $route.reload();
                },
                function failure(details) {
                    angular.copy($scope.rnodeDup, $scope.rnode)
                    Notifications.set('edit', 'error',
                        "Could not save submission category: " + details.statusText);
                }
            );
        };

        $scope.demoStats = [
            {
                name: 'Final',
                value: 120,
                fraction: 1.0
            },
            {
                name: 'Reviewed',
                value: 80,
                fraction: 0.75
            },
            {
                name: 'Approved',
                value: 60,
                fraction: 0.5
            },
        ];
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
}])


.controller('StatisticsCtrl', [
        '$scope', 'QuestionNode', 'routeData', 'Editor', 'questionAuthz',
        '$location', 'Notifications', 'Current', 'format', 'Structure',
        'layout', 'Arrays', 'ResponseNode', 'Statistics', 'Assessment',
        '$timeout',
        function($scope, QuestionNode, routeData, Editor, authz,
                 $location, Notifications, current, format, Structure,
                 layout, Arrays, ResponseNode, Statistics, Assessment,
                 $timeout) {

    var boxQuartiles = function(d) {
        var quartiles = [];
        angular.forEach(d.data, function(item, index) {
            quartiles.push([
                item.quartile[0],
                item.quartile[1],
                item.quartile[2]
            ]);
        });
        return quartiles;
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
                tspan = text.text(null).append("tspan")
                    .attr("x", 0).attr("y", y).attr("dy", dy + "em");
            while (word = words.pop()) {
              line.push(word);
              tspan.text(line.join(" "));
              if (tspan.node().getComputedTextLength() > width) {
                line.pop();
                tspan.text(line.join(" "));
                line = [word];
                tspan = text.append("tspan")
                    .attr("x", 0).attr("y", y)
                    .attr("dy", ++lineNumber * lineHeight + dy + "em")
                    .text(word);
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
                var g = d3.select(this),
                    n = d.length;

                var checkOverlapping = 
                    function(tickValues, itemValue, itemIndex, yAxis) {
                        var gap = 0;
                        angular.forEach(tickValues, function(tick, index) {
                            if (index != itemIndex && 
                                Math.abs(yAxis(itemValue)-yAxis(tick)) < 7)
                                gap = 10;
                        });
                        return gap;
                };

                var displayChart = function (object, dataIndex, compareMode) {
                    var lineWidth = !object.compareMode ? width : width / 2 - 1;
                    var data = object.data[dataIndex];
                    // Compute the new x-scale.
                    var yAxis = d3.scale.linear()
                      .domain([data.min, data.max])
                      .range([height - 40, 20]);

                     // Compute the tick format.
                    var format = tickFormat || yAxis.tickFormat(8);
                    var line20 = (data.max - data.min) * 0.2;
                    var borderData = [data.min, 
                                      data.min + line20, 
                                      data.min + line20 * 2, 
                                      data.min + line20 * 3, 
                                      data.min + line20 * 4, 
                                      data.max];
                    var borderClass = ["border", 
                                       "border20",
                                       "border20",
                                       "border20",
                                       "border20",
                                       "border"]

                    if (dataIndex==0) {
                        var border = g.selectAll("line.border")
                            .data(borderData);

                        border.enter().insert("line")
                            .attr("class", function(item, i) { 
                                return borderClass[i]; 
                            })
                            .attr("x1", -50)
                            .attr("y1", yAxis)
                            .attr("x2", 70)
                            .attr("y2", yAxis);
                    }

                    g.append("line", "rect")
                        .attr("class", "center")
                        .attr("x1", width / 2)
                        .attr("y1", yAxis(data.survey_min))
                        .attr("x2", width / 2)
                        .attr("y2", yAxis(data.survey_max));

                    // Update innerquartile box.
                    g.append("rect")
                        .attr("class", "box")
                        .attr("x", (dataIndex==0 ? 0: width/2) + 0.5)
                        .attr("y", Math.round(yAxis(data.quartile[2])) + 0.5)
                        .attr("width", lineWidth)
                        .attr("height", Math.round(yAxis(data.quartile[0])
                                - yAxis(data.quartile[2])) - 1);

                    // Update whisker ticks. These are handled separately from the box
                    // ticks because they may or may not exist, and we want don't want
                    // to join box ticks pre-transition with whisker ticks post-.
                    var tickData = [data.min,                   // 0
                                    data.survey_min,            // 1
                                    data.quartile[1],           // 2
                                    data.current,               // 3
                                    data.survey_max,            // 4
                                    data.max];                  // 5

                    var tickClass = ["whisker_text",
                                     "whisker_text",
                                     "median_text",
                                     "current_text",
                                     "whisker_text",
                                     "whisker_text"];

                    // text tick
                    g.selectAll("text.whisker" + dataIndex)
                        .data(tickData)
                        .enter().append("text")
                        .attr("class", function(item, index) {
                            return "tick " + tickClass[index];
                        })
                        .attr("dy", ".3em")
                        .attr("dx", dataIndex==0 ? -30:5)
                        .attr("x", width)
                        .attr("y", function(item, index) {
                            // top and bottom value display
                            if (index==0) 
                                return yAxis(item)+13;
                            if (index==5) 
                                return yAxis(item)-10;
                            var gap = 0;
                            if (index != 3)
                                gap = checkOverlapping(tickData, item, index, 
                                    yAxis);

                            return yAxis(item) + gap;
 
                        })
                        .attr("text-anchor", dataIndex==0 ? "end":"start")
                        .text(format);

                    var lineData = [data.survey_min,            // 0
                                    data.survey_max,            // 1
                                    data.quartile[1],           // 2
                                    data.current];              // 3

                    var lineClass = ["whisker",
                                     "whisker",
                                     "median",
                                     "current"];

                    g.selectAll("line.whisker" + dataIndex)
                        .data(lineData)
                        .enter().append("line")
                        .attr("class", function(item, index) {
                            return lineClass[index]; 
                        })
                        .attr("x1", function(item, index) {
                            if(index == 3)
                                return dataIndex==0 ? -4:width/2;
                            return dataIndex==0 ? 0:width/2; 
                        })
                        .attr("y1", function(item, index) {
                            return Math.round(yAxis(item));
                        })
                        .attr("x2", function(item, index) {
                            if(compareMode) {
                                if(index == 3)
                                    return dataIndex==0 ? width/2:width+5;
                                return dataIndex==0 ? width/2:width;
                            } else {
                                if(index == 3)
                                    return width+5;
                                return width + 1;
                            }
                        })
                        .attr("y2", function(item, index) {
                            return Math.round(yAxis(item));
                        });

                    if (dataIndex == 0) {
                        g.append("text")
                            .attr("class", "title")
                            .attr("x", 0)
                            .attr("y", yAxis(0) - 20)
                            .attr("dy", 5)
                            .attr("text-anchor", "middle")
                            .text(d.title)
                            .call(wrap, 100);
                    }
                };

                displayChart(d, 0, d.compareMode);

                if (d.compareMode) {
                    displayChart(d, 1, d.compareMode);
                }
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

    // Start custom logic here
    $scope.assessment1 = routeData.assessment1;
    $scope.assessment2 = routeData.assessment2;
    $scope.rnodes1 = routeData.rnodes1;
    $scope.rnodes2 = routeData.rnodes2;
    $scope.stats1 = routeData.stats1;
    $scope.stats2 = routeData.stats2;
    $scope.qnode1 = routeData.qnode1;
    $scope.qnode2 = routeData.qnode2;
    $scope.approval = routeData.approval;
    $scope.struct1 = Structure(
        routeData.qnode1 || routeData.assessment1.hierarchy,
        routeData.assessment1);
    if (routeData.assessment2) {
        $scope.struct2 = Structure(
            routeData.qnode2 || routeData.assessment2.hierarchy,
            routeData.assessment2);
    }
    $scope.layout = layout;

    $scope.getAssessmentUrl1 = function(assessment) {
        var query;
        if (assessment) {
            query = format('assessment1={}&assessment2={}',
                assessment.id,
                $scope.assessment2 ? $scope.assessment2.id : '');
        } else {
            query = format('assessment1={}',
                $scope.assessment2 ? $scope.assessment2.id : '');
        }
        return format('/statistics?{}&qnode={}&approval={}',
            query, $location.search()['qnode'] || '', $scope.approval);
    };
    $scope.getAssessmentUrl2 = function(assessment) {
        var query;
        if (assessment) {
            query = format('assessment1={}&assessment2={}',
                $scope.assessment1 ? $scope.assessment1.id : '',
                assessment.id);
        } else {
            query = format('assessment1={}',
                $scope.assessment1 ? $scope.assessment1.id : '');
        }
        return format('/statistics?{}&qnode={}&approval={}',
            query, $location.search()['qnode'] || '', $scope.approval);
    };

    $scope.getNavUrl = function(item, key) {
        var aid1 = $scope.assessment1.id;
        var aid2 = $scope.assessment2 ? $scope.assessment2.id : ''
        if (item.path == 'qnode') {
            return format(
                '#/statistics?assessment1={}&assessment2={}&qnode={}&approval={}',
                aid1, aid2, key, $scope.approval);
        } else if (item.path == 'assessment') {
            return format(
                '#/statistics?assessment1={}&assessment2={}&approval={}',
                aid1, aid2, $scope.approval);
        }
        return null;
    };

    $scope.chooser = false;
    $scope.toggleDropdown = function(num) {
        if ($scope.chooser == num)
            $scope.chooser = null;
        else
            $scope.chooser = num;
    };


    $scope.setState = function(approval) {
        $location.search('approval', approval);
    };

    var margin = {top: 10, right: 50, bottom: 20, left: 50},
        width = 120 - margin.left - margin.right,
        height = 600 - margin.top - margin.bottom;

    var chart = d3.box()
        .whiskers()
        .width(width)
        .height(height);

    var svg = d3.select("#chart").selectAll("svg");

    var data = [];

    var drawChart = function() {
        if (data.length > 0) {
            svg.data(data)
                .enter().append("svg")
                    .attr("class", "box")
                    .attr("width", width + margin.left + margin.right)
                    .attr("height", height + margin.bottom + margin.top)
                    .on("click", function(d) {
                        $location.search('qnode', d.id);
                    })
                .append("g")
                    .attr("transform",
                          "translate(" + margin.left + "," + margin.top + ")")
                    .call(chart);
        } else {
            var svgContainer = svg.data(["No Data"]).enter().append("svg")
                .attr("width", 1000)
                .attr("height", height);
            svgContainer.append("text")
                .attr("x", 500)
                .attr("y", height / 4)
                .attr("text-anchor", "middle")
                .attr("class", "info")
                .text("No Data");
        }

    };

    var fillData = function(assessment, rnodes, stats) {
        if (rnodes.length == 0)
            return;

        if (data.length == 0) {
            for (var i = 0; i < rnodes.length; i++) {
                var node = rnodes[i];
                var stat = stats.filter(function(s) {
                    if(s.qnodeId == node.qnode.id) {
                        return s;
                    }
                });
                if (stat.length) {
                    stat = stat[0];
                    var item = {'id': node.qnode.id, 'compareMode': false, 
                             'data': [], 'title' : stat.title };
                    item['data'].push({
                                        'current': node.score,
                                        'max': node.qnode.totalWeight,
                                        'min': 0,
                                        'survey_max': stat.max,
                                        'survey_min': stat.min,
                                        'quartile': stat.quartile});
                    data.push(item);
                }
            };

        } else {
            for (var i = 0; i < data.length; i++) {
                var item = data[i];
                item["compareMode"] = true;
                var stat = stats.filter(function(s) {
                    if(s.qnodeId == item.id) {
                        return s;
                    }
                });
                var node = rnodes.filter(function(n) {
                    if(n.qnode.id == item.id) {
                        return n;
                    }
                });

                if (stat.length && node.length) {
                    stat = stat[0];
                    node = node[0];
                    item['data'].push({
                                        'current': node.score,
                                        'max': node.qnode.totalWeight,
                                        'min': 0,
                                        'survey_max': stat.max,
                                        'survey_min': stat.min,
                                        'quartile': stat.quartile});

                } else {
                    item['data'].push({
                                        'current': 0,
                                        'max': 0,
                                        'min': 0,
                                        'survey_max': 0,
                                        'survey_min': 0,
                                        'quartile': [0, 0, 0]});
                }
            };
        }
    };

    fillData($scope.assessment1, $scope.rnodes1, $scope.stats1);
    if ($scope.assessment2)
        fillData($scope.assessment2, $scope.rnodes2, $scope.stats2);

    drawChart();
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

    $scope.search = {
        deleted: false
    };
    $scope.$watchGroup(['search.deleted', 'hierarchy.id',
                        'assessment.hierarchy.id', 'qnode.id'], function(vars) {
        var deleted = vars[0];
        var hid = vars[1] || vars[2];
        var qid = vars[3];
        if (!hid && !qid)
            return;

        QuestionNode.query({
            parentId: qid,
            hierarchyId: hid,
            surveyId: $scope.survey.id,
            root: qid ? undefined : '',
            deleted: deleted
        }, function(children) {
            $scope.children = children;
        });
    });

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
                        notRelevant: rnode.nNotRelevant >= nm,
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
                        ],
                        importance: rnode.maxImportance,
                        urgency: rnode.maxUrgency,
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
        ],
        importance: 0,
        urgency: 0,
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

    if ($scope.assessment) {
        $scope.query = 'assessment=' + $scope.assessment.id;
    } else {
        $scope.query = 'survey=' + $scope.survey.id;
        $scope.query += "&parent=" + $scope.qnode.id;
    }

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


.controller('DiffCtrl', [
        '$scope', 'QuestionNode', 'routeData', 'Editor', 'questionAuthz',
        '$location', 'Notifications', 'Current', 'format', 'Structure',
        'Enqueue', 'Diff', '$timeout',
        function($scope, QuestionNode, routeData, Editor, authz,
                 $location, Notifications, current, format, Structure,
                 Enqueue, Diff, $timeout) {

    $scope.hierarchy1 = routeData.hierarchy1;
    $scope.hierarchy2 = routeData.hierarchy2;
    $scope.survey1 = $scope.hierarchy1.survey;
    $scope.survey2 = $scope.hierarchy2.survey;

    $scope.diff = null;

    $scope.tags = [
        'context', 'added', 'deleted', 'modified',
        'reordered', 'relocated', 'list index'];

    $scope.updateTags = function() {
        var ignoreTags = $location.search()['ignoreTags'];
        if (angular.isString(ignoreTags))
            ignoreTags = [ignoreTags];
        else if (ignoreTags == null)
            ignoreTags = [];
        $scope.ignoreTags = ignoreTags;
    };
    $scope.update = Enqueue(function() {
        $scope.longRunning = false;
        $scope.diff = Diff.get({
            surveyId1: $scope.survey1.id,
            surveyId2: $scope.survey2.id,
            hierarchyId: $scope.hierarchy1.id,
            ignoreTag: $scope.ignoreTags
        });
        $timeout(function() {
            $scope.longRunning = true;
        }, 5000);
    }, 1000);
    $scope.$on('$routeUpdate', function(scope, next, current) {
        $scope.updateTags();
        $scope.update();
    });
    $scope.updateTags();
    $scope.update();

    $scope.toggleTag = function(tag) {
        var i = $scope.ignoreTags.indexOf(tag);
        if (i >= 0)
            $scope.ignoreTags.splice(i, 1);
        else
            $scope.ignoreTags.push(tag);
        $location.search('ignoreTags', $scope.ignoreTags);
    };
    $scope.tagEnabled = function(tag) {
        return $scope.ignoreTags.indexOf(tag) < 0;
    };

    $scope.getItemUrl = function(item, entity, survey) {
        if (item.type == 'qnode')
            return format("/qnode/{}?survey={}", entity.id, survey.id);
        else if (item.type == 'measure')
            return format("/measure/{}?survey={}&parent={}",
                entity.id, survey.id, entity.parentId);
        else if (item.type == 'survey')
            return format("/survey/{}", survey.id);
        else if (item.type == 'hierarchy')
            return format("/hierarchy/{}?survey={}", entity.id, survey.id);
    };

    $scope.chooser = false;
    $scope.toggleDropdown = function(num) {
        if ($scope.chooser == num)
            $scope.chooser = null;
        else
            $scope.chooser = num;
    };

}])


.controller('QnodeLinkCtrl', [
        '$scope', 'QuestionNode', 'routeData', 'questionAuthz',
        '$location', 'Notifications', 'Current', 'format',
        'layout', 'Structure',
        function($scope, QuestionNode, routeData, authz,
                 $location, Notifications, current, format,
                 layout, Structure) {

    $scope.layout = layout;
    $scope.hierarchy = routeData.hierarchy;
    $scope.parent = routeData.parent;
    $scope.survey = routeData.survey;

    $scope.qnode = {
        hierarchy: $scope.parent || $scope.hierarchy,
        parent: $scope.parent
    };
    $scope.structure = Structure($scope.qnode);

    $scope.select = function(qnode) {
        // postData is empty: we don't want to update the contents of the
        // qnode; just its links to parents (giving in query string).
        var postData = {};
        QuestionNode.save({
            id: qnode.id,
            parentId: $scope.parent.id,
            surveyId: $scope.survey.id
        }, postData,
            function success(measure, headers) {
                var message = "Saved";
                if (headers('Operation-Details'))
                    message += ': ' + headers('Operation-Details');
                Notifications.set('edit', 'success', message);
                $location.url(format(
                    '/qnode/{}?survey={}', $scope.parent.id, $scope.survey.id));
            },
            function failure(details) {
                Notifications.set('edit', 'error',
                    "Could not save object: " + details.statusText);
            }
        );
    };

    $scope.search = {
        level: $scope.structure.qnodes.length - 1,
        parent__not: $scope.parent ? $scope.parent.id : '',
        term: "",
        deleted: false,
        surveyId: $scope.survey.id,
        hierarchyId: $scope.structure.hierarchy.id,
        desc: true,
        page: 0,
        pageSize: 10
    };
    $scope.$watch('search', function(search) {
        QuestionNode.query(search).$promise.then(function(qnodes) {
            $scope.qnodes = qnodes;
        });
    }, true);

    $scope.checkRole = authz(current, $scope.survey);
    $scope.QuestionNode = QuestionNode;
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
        }, postData,
            function success(measure, headers) {
                var message = "Saved";
                if (headers('Operation-Details'))
                    message += ': ' + headers('Operation-Details');
                Notifications.set('edit', 'success', message);
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
        'Structure', 'Arrays', 'Response', 'hotkeys', '$q', '$timeout', '$window',
        function($scope, Measure, routeData, Editor, authz,
                 $location, Notifications, current, Survey, format, layout,
                 Structure, Arrays, Response, hotkeys, $q, $timeout, $window) {

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
        // Create an empty response for the time being so the response control
        // doesn't create its own.
        $scope.lastSavedResponse = null;
        $scope.setResponse = function(response) {
            $scope.response = response;
            $scope.lastSavedResponse = angular.copy(response);
        };

        $scope.setResponse({
            responseParts: [],
            comment: ''
        });
        Response.get({
            measureId: $scope.measure.id,
            assessmentId: $scope.assessment.id
        }).$promise.then(
            function success(response) {
                $scope.setResponse(response);
            },
            function failure(details) {
                if (details.status != 404) {
                    Notifications.set('edit', 'error',
                        "Failed to get response details: " + details.statusText);
                    return;
                }
                $scope.setResponse(new Response({
                    measureId: $scope.measure.id,
                    assessmentId: $scope.assessment.id,
                    responseParts: [],
                    comment: '',
                    notRelevant: false,
                    approval: 'draft'
                }));
            }
        );

        var interceptingLocation = false;
        $scope.$on('$locationChangeStart', function(event, next, current) {
            if (!$scope.response.$dirty || interceptingLocation)
                return;
            event.preventDefault();
            interceptingLocation = true;
            $scope.saveResponse().then(
                function success() {
                    $window.location.href = next;
                    $timeout(function() {
                        interceptingLocation = false;
                    });
                },
                function failure(details) {
                    var message = "Failed to save: " +
                        details.statusText +
                        ". Are you sure you want to leave this page?";
                    var answer = confirm(message);
                    if (answer)
                        $window.location.href = next;
                    $timeout(function() {
                        interceptingLocation = false;
                    });
                }
            );
        });

        $scope.saveResponse = function() {
            return $scope.response.$save().then(
                function success(response) {
                    $scope.$broadcast('response-saved');
                    Notifications.set('edit', 'success', "Saved", 5000);
                    $scope.setResponse(response);
                    return response;
                },
                function failure(details) {
                    Notifications.set('edit', 'error',
                        "Could not save response: " + details.statusText);
                    return $q.reject(details);
                });
        };
        $scope.resetResponse = function() {
            $scope.response = angular.copy($scope.lastSavedResponse);
        };
        $scope.toggleNotRelvant = function() {
            var oldValue = $scope.response.notRelevant;
            $scope.response.notRelevant = !oldValue;
            $scope.response.$save().then(
                function success(response) {
                    Notifications.set('edit', 'success', "Saved", 5000);
                    $scope.setResponse(response);
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
                function success(response) {
                    Notifications.set('edit', 'success', "Saved", 5000);
                    $scope.setResponse(response);
                },
                function failure(details) {
                    Notifications.set('edit', 'error',
                        "Could not save response: " + details.statusText);
                }
            );
        };
        $scope.$watch('response', function() {
            $scope.response.$dirty = !angular.equals(
                $scope.response, $scope.lastSavedResponse);
        }, true);
    }

    $scope.$watch('measure', function(measure) {
        $scope.structure = Structure(measure, $scope.assessment);
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
            !$scope.structure.deletedItem &&
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
            return format('/measure/{}?assessment={}',
                $scope.measure.id, assessment.id,
                $scope.parent && $scope.parent.id || '');
        } else {
            return format('/measure/{}?survey={}&parent={}',
                $scope.measure.id, $scope.survey.id,
                $scope.measure.parent && $scope.measure.parent.id || '');
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
        dropzone.options.autoProcessQueue = false;
        $scope.showFileDrop = false;
        dropzone.removeAllFiles();
        $scope.refreshAttachments();
    });

    dropzone.on("error", function(file, details, request) {
        var error;
        if (request) {
            error = "Upload failed: " + request.statusText;
        } else {
            error = details;
        }
        dropzone.options.autoProcessQueue = false;
        dropzone.removeAllFiles();
        Notifications.set('attach', 'error', error);
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


.factory('CustomQueryConfig', ['$resource', function($resource) {
    return $resource('/adhoc_query.json', {}, {
        get: { method: 'GET', cache: false }
    });
}])


.factory('SampleQueries', ['$resource', function($resource) {
    return $resource('/sample_queries.json', {}, {
        get: { method: 'GET', isArray: true, cache: false }
    });
}])


.controller('AdHocCtrl', ['$scope', '$http', 'Notifications', 'samples',
            'hotkeys', 'config',
            function($scope, $http, Notifications, samples, hotkeys, config) {
    $scope.config = config;
    $scope.query = samples[0].query;
    $scope.result = {};
    $scope.samples = samples;
    $scope.execLimit = 20;

    $scope.execute = function(query) {
        var config = {
            params: {limit: $scope.execLimit}
        };
        $http.post('/adhoc_query.json', query, config).then(
            function success(response) {
                var message = "Query finished";
                if (response.headers('Operation-Details'))
                    message += ': ' + response.headers('Operation-Details');
                Notifications.set('query', 'info', message, 5000);

                $scope.result = angular.fromJson(response.data);
            },
            function failure(response) {
                Notifications.set('query', 'error',
                    "Error: " + response.statusText);
            }
        );
    };

    $scope.download = function(query, file_type) {
        $http.post('/adhoc_query.' + file_type, query,
                   {responseType: 'blob'}).then(
            function success(response) {
                var message = "Query finished";
                if (response.headers('Operation-Details'))
                    message += ': ' + response.headers('Operation-Details');
                Notifications.set('query', 'info', message, 5000);

                var blob = new Blob(
                    [response.data], {type: response.headers('Content-Type')});
                var name = /filename=(.*)/.exec(
                    response.headers('Content-Disposition'))[1];
                saveAs(blob, name);
            },
            function failure(response) {
                Notifications.set('query', 'error',
                    "Error: " + response.statusText);
            }
        );
    };

    $scope.format = function(query) {
        $http.post('/reformat.sql', $scope.query).then(
            function success(response) {
                $scope.query = response.data;
                Notifications.set('query', 'info', "Formatted", 5000);
            },
            function failure(response) {
                Notifications.set('query', 'error',
                    "Error: " + response.statusText);
            }
        );
    };

    $scope.setQuery = function(query) {
        $scope.query = query;
    };

    $scope.colClass = function($index) {
        var col = $scope.result.cols[$index];
        if (col.richType == 'int' || col.richType == 'float')
            return 'numeric';
        else if (col.richType == 'uuid')
            return 'med-truncated';
        else if (col.richType == 'text')
            return 'str-wrap';
        else if (col.richType == 'json')
            return 'pre-wrap';
        else if (col.type == 'date')
            return 'date';
        else
            return null;
    };
    $scope.colRichType = function($index) {
        var col = $scope.result.cols[$index];
        return col.richType;
    };

    hotkeys.bindTo($scope)
        .add({
            combo: ['ctrl+enter'],
            description: "Execute query",
            allowIn: ['TEXTAREA'],
            callback: function(event, hotkey) {
                $scope.execute($scope.query);
            }
        });
}])


;
