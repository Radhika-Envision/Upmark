'use strict';

angular.module('wsaa.surveyQuestions', [
    'ngResource', 'ngSanitize',
    'ui.select', 'ui.sortable',
    'wsaa.admin', 'wsaa.survey.services'])


.factory('questionAuthz', ['Roles', function(Roles) {
    return function(current, program, submission) {
        var ownOrg = false;
        var org = submission && submission.organisation || null;
        if (org)
            ownOrg = org.id == current.user.organisation.id;
        else
            ownOrg = true;
        return function(functionName) {
            switch(functionName) {
                case 'program_dup':
                case 'program_state':
                    return Roles.hasPermission(current.user.role, 'admin');
                    break;
                case 'submission_add':
                    return Roles.hasPermission(current.user.role, 'clerk');
                    break;
                case 'submission_browse':
                    return Roles.hasPermission(current.user.role, 'clerk') ||
                        Roles.hasPermission(current.user.role, 'consultant');
                    break;
                case 'submission_review':
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
                case 'submission_admin':
                    if (Roles.hasPermission(current.user.role, 'consultant'))
                        return true;
                    if (Roles.hasPermission(current.user.role, 'org_admin'))
                        return ownOrg;
                    break;
                case 'submission_edit':
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


.controller('ProgramCtrl',
        function($scope, Program, routeData, Editor, questionAuthz, hotkeys,
                 $location, Notifications, Current, Survey, layout, format,
                 $http, Organisation, Submission) {

    $scope.layout = layout;
    if (routeData.program) {
        // Viewing old
        $scope.edit = Editor('program', $scope);
        $scope.program = routeData.program;
        $scope.surveys = routeData.surveys;
        $scope.duplicating = false;
    } else if (routeData.duplicate) {
        // Duplicating existing
        $scope.edit = Editor('program', $scope,
            {duplicateId: routeData.duplicate.id});
        $scope.program = routeData.duplicate;
        $scope.program.id = null;
        $scope.program.title = $scope.program.title + " (duplicate)"
        $scope.surveys = null;
        $scope.edit.edit();
        $scope.duplicating = true;
    } else {
        // Creating new
        $scope.edit = Editor('program', $scope);
        $scope.program = new Program({
            responseTypes: []
        });
        $scope.surveys = null;
        $scope.edit.edit();
        $scope.duplicating = false;
    }

    $scope.$on('EditSaved', function(event, model) {
        $location.url('/1/program/' + model.id);
    });
    $scope.$on('EditDeleted', function(event, model) {
        $location.url('/1/programs');
    });

    $scope.checkRole = questionAuthz(Current, $scope.program);

    $scope.toggleEditable = function() {
        $scope.program.$save({editable: !$scope.program.isEditable},
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
        if (!$scope.program.id)
            return;
        Survey.query({
            programId: $scope.program.id,
            deleted: $scope.search.deleted
        }, function success(surveys) {
            $scope.surveys = surveys
        }, function failure(details) {
                Notifications.set('edit', 'error',
                    "Could not get list of surveys: " + details.statusText);
        });
    });

    $scope.Program = Program;

    hotkeys.bindTo($scope)
        .add({
            combo: ['a'],
            description: "Add a new question set",
            callback: function(event, hotkey) {
                $location.url(
                    format("/1/survey/new?program={{}}", $scope.program.id));
            }
        })
        .add({
            combo: ['s'],
            description: "Search for measures",
            callback: function(event, hotkey) {
                $location.url(
                    format("/1/measures?program={{}}", $scope.program.id));
            }
        });
})


.directive('submissionHeader', [function() {
    return {
        templateUrl: 'submission_header.html',
        replace: true,
        scope: true,
        controller: ['$scope', function($scope) {
            $scope.showSubmissionChooser = false;
            $scope.toggleDropdown = function() {
                $scope.showSubmissionChooser = !$scope.showSubmissionChooser;
            };
        }]
    }
}])


.directive('submissionSelect', [function() {
    return {
        restrict: 'AEC',
        templateUrl: 'submission_select.html',
        scope: {
            submission: '=submissionSelect',
            org: '=',
            program: '=',
            track: '@',
            survey: '=',
            formatUrl: '=',
            disallowNone: '='
        },
        controller: ['$scope', 'Current', 'Submission', 'Organisation',
                '$location', 'format', 'Notifications', 'PurchasedSurvey',
                'Structure', 'questionAuthz', 'Enqueue',
                function($scope, current, Submission, Organisation,
                         $location, format, Notifications, PurchasedSurvey,
                         Structure, authz, Enqueue) {

            $scope.aSearch = {
                organisation: null,
                historical: false
            };

            $scope.$watch('submission.organisation', function(org) {
                if (!org)
                    org = $scope.org || current.user.organisation;
                $scope.aSearch.organisation = org;
            });

            $scope.searchOrg = function(term) {
                return Organisation.query({term: term}).$promise;
            };
            $scope.$watch('aSearch.organisation', function(organisation) {
                if (organisation)
                    $scope.search.orgId = organisation.id;
                else
                    $scope.search.orgId = null;
            });

            $scope.$watch('survey', function(survey) {
                $scope.search.surveyId = survey ? survey.id : null;
            });

            $scope.$watchGroup(['program', 'aSearch.historical'], function(vars) {
                var program = vars[0],
                    historical = vars[1];

                if (historical) {
                    $scope.search.trackingId = program ? program.trackingId : null;
                    $scope.search.programId = null;
                } else {
                    $scope.search.trackingId = null;
                    $scope.search.programId = program ? program.id : null;
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
                surveyId: null,
                programId: null,
                trackingId: null,
                deleted: false,
                page: 0,
                pageSize: 5
            };
            $scope.applySearch = Enqueue(function() {
                Submission.query($scope.search).$promise.then(
                    function success(submissions) {
                        $scope.submissions = submissions;
                    },
                    function failure(details) {
                        Notifications.set('program', 'error',
                            "Could not get submission list: " + details.statusText);
                    }
                );
            }, 100);
            $scope.$watch('search', $scope.applySearch, true);

            $scope.$watchGroup(['program', 'search.orgId', 'survey', 'track'],
                    function(vars) {

                var program = vars[0];
                var orgId = vars[1];
                var survey = vars[2];
                var track = vars[3];

                if (!program || !orgId || !survey || track != null) {
                    $scope.purchasedSurvey = null;
                    return;
                }

                PurchasedSurvey.head({
                    programId: program.id,
                    id: orgId,
                    hid: survey.id
                }, null, function success(purchasedSurvey) {
                    $scope.purchasedSurvey = purchasedSurvey;
                }, function failure(details) {
                    if (details.status == 404) {
                        $scope.purchasedSurvey = null;
                        return;
                    }
                    Notifications.set('program', 'error',
                        "Could not get purchase status: " + details.statusText);
                });
            });

            // Allow parent controller to specify a special URL formatter - this
            // is so one can switch between submissions without losing one's
            // place in the survey.
            $scope.getSubmissionUrl = function(submission) {
                if ($scope.formatUrl)
                    return $scope.formatUrl(submission)

                if (submission) {
                    return format('/1/submission/{}', submission.id);
                } else {
                    return format('/1/survey/{}?program={}',
                        $scope.survey.id, $scope.program.id);
                }
            };

            $scope.checkRole = authz(current, $scope.program);
        }]
    }
}])


.controller('ProgramListCtrl', ['$scope', 'questionAuthz', 'Program', 'Current',
        'layout',
        function($scope, authz, Program, current, layout) {

    $scope.layout = layout;
    $scope.checkRole = authz(current, null);

    $scope.search = {
        term: "",
        editable: $scope.checkRole('program_edit'),
        deleted: false,
        page: 0,
        pageSize: 10
    };
    $scope.$watch('search', function(search) {
        Program.query(search).$promise.then(function(programs) {
            $scope.programs = programs;
        });
    }, true);
}])


.controller('ProgramImportCtrl', [
        '$scope', 'Program', 'hotkeys', '$location', '$timeout',
        'Notifications', 'layout', 'format', '$http', '$cookies',
        function($scope, Program, hotkeys, $location, $timeout,
                 Notifications, layout, format, $http, $cookies) {

    $scope.progress = {
        isWorking: false,
        isFinished: false,
        uploadFraction: 0.0
    };
    Notifications.remove('import');
    $scope.program = {
        title: "Imported Program",
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
        formData.append('title', $scope.program.title);
        formData.append('description', $scope.program.description);
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
            $location.url('/1/program/' + response);
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
.directive('programHistory', [function() {
    return {
        restrict: 'E',
        templateUrl: '/program_history.html',
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
                    $scope.programs = $scope.service.history({
                        id: $scope.entity.id,
                        deleted: false
                    });
                }
            };

            $scope.navigate = function(program) {
                if ($scope.entity == $scope.structure.program)
                    $location.url('/1/program/' + program.id);
                else
                    $location.search('program', program.id);
            };
            $scope.isActive = function(program) {
                if ($scope.entity == $scope.structure.program)
                    return $location.url().indexOf('/1/program/' + program.id) >= 0;
                else
                    return $location.search().program == program.id;
            };

            $scope.compare = function(program, event) {
                var s1, s2;
                if (program.created < $scope.structure.program.created) {
                    s1 = program;
                    s2 = $scope.structure.program;
                } else {
                    s1 = $scope.structure.program;
                    s2 = program;
                }
                var url = format(
                    '/1/diff/{}/{}/{}?ignoreTags=list+index',
                    s1.id,
                    s2.id,
                    $scope.structure.survey.id);
                $location.url(url);
                event.preventDefault();
                event.stopPropagation();
            };
        }]
    };
}])


.factory('Structure', function() {
    return function(entity, submission) {
        var stack = [];
        while (entity) {
            stack.push(entity);
            if (entity.obType == 'measure')
                entity = entity.parent || entity.program;
            else if (entity.obType == 'qnode')
                entity = entity.parent || entity.survey;
            else if (entity.obType == 'survey')
                entity = entity.program;
            else if (entity.obType == 'program')
                entity = null;
            else
                entity = null;
        }
        stack.reverse();

        var hstack = [];
        var program = null;
        var survey = null;
        var measure = null;
        // Program
        if (stack.length > 0) {
            program = stack[0];
            hstack.push({
                path: 'program',
                title: 'Program',
                label: 'Pg',
                entity: program,
                level: 's'
            });
        }
        // Survey, or orphaned measure
        if (stack.length > 1) {
            if (stack[1].obType == 'measure') {
                measure = stack[1];
                hstack.push({
                    path: 'measure',
                    title: 'Measures',
                    label: 'M',
                    entity: measure,
                    level: 'm'
                });
            } else {
                survey = stack[1];
                hstack.push({
                    path: 'survey',
                    title: 'Surveys',
                    label: 'Sv',
                    entity: survey,
                    level: 'h'
                });
            }
        }

        if (submission) {
            // Submissions slot in after survey.
            hstack.splice(2, 0, {
                path: 'submission',
                title: 'Submissions',
                label: 'Sb',
                entity: submission,
                level: 'h'
            });
        }

        var qnodes = [];
        if (stack.length > 2 && survey) {
            var qnodeMaxIndex = stack.length - 1;
            if (stack[stack.length - 1].obType == 'measure') {
                measure = stack[stack.length - 1];
                qnodeMaxIndex = stack.length - 2;
            } else {
                measure = null;
                qnodeMaxIndex = stack.length - 1;
            }

            var structure = survey.structure;
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
            program: program,
            survey: survey,
            submission: submission,
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
            submission: '=',
            getUrl: '='
        },
        replace: true,
        templateUrl: 'question_header.html',
        controller: ['$scope', 'layout', 'Structure', 'hotkeys', 'format',
                '$location',
                function($scope, layout, Structure, hotkeys, format, $location) {
            $scope.layout = layout;
            $scope.$watchGroup(['entity', 'submission'], function(vals) {
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

                var path = format("#/1/{}/{}", item.path, key);
                var query = [];
                if (item.path == 'program' || item.path == 'submission') {
                } else if (item.path == 'survey') {
                    query.push('program=' + $scope.structure.program.id);
                } else {
                    if ($scope.submission)
                        query.push('submission=' + $scope.submission.id);
                    else
                        query.push('program=' + $scope.structure.program.id);
                }
                if (item.path == 'measure' && item.entity.parent
                        && !$scope.submission) {
                    query.push('parent=' + item.entity.parent.id);
                }
                url = path + '?' + query.join('&');

                return url;
            };

            hotkeys.bindTo($scope)
                .add({
                    combo: ['u'],
                    description: "Go up one level of the survey",
                    callback: function(event, hotkey) {
                        var url = $scope.itemUrl($scope.upItem);
                        if (!url)
                            url = '/1/programs';
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


.controller('SurveyChoiceCtrl', [
        '$scope', 'routeData', 'Structure', 'questionAuthz', 'Current',
        'Survey', 'layout', '$location', 'Roles',
        function($scope, routeData, Structure, questionAuthz, current,
                 Survey, layout, $location, Roles) {
    $scope.layout = layout;
    $scope.program = routeData.program;
    $scope.survey = routeData.survey;
    $scope.org = routeData.org;
    $scope.structure = Structure($scope.survey);

    if (current.user.role == 'author')
        $location.path('/1/survey/' + $scope.survey.id);

    $scope.Survey = Survey;
    $scope.checkRole = questionAuthz(current, $scope.program);
}])


.controller('SurveyCtrl', [
        '$scope', 'Survey', 'routeData', 'Editor', 'questionAuthz', 'layout',
        '$location', 'Current', 'format', 'QuestionNode', 'Structure', '$http',
        'Notifications',
        function($scope, Survey, routeData, Editor, authz, layout,
                 $location, current, format, QuestionNode, Structure, $http,
                 Notifications) {

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
            '/1/survey/{}?program={}', model.id, $scope.program.id));
    });
    $scope.$on('EditDeleted', function(event, model) {
        $location.url(format(
            '/1/program/{}', $scope.program.id));
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
        var url = '/export/program/' + $scope.program.id;
        url += '/survey/' + $scope.survey.id;
        url += '/' + export_type + '.xlsx';

        $http.get(url, { responseType: "arraybuffer", cache: false }).then(
            function success(response) {
                var message = "Export finished";
                Notifications.set('export', 'info', message, 5000);
                var blob = new Blob(
                    [response.data], {type: response.headers('Content-Type')});
                var name = /filename=(.*)/.exec(
                    response.headers('Content-Disposition'))[1];
                saveAs(blob, name);
            },
            function failure(response) {
                Notifications.set('export', 'error',
                    "Error: " + response.statusText);
            }
        );
    };

    $scope.checkRole = authz(current, $scope.program);
    $scope.QuestionNode = QuestionNode;
    $scope.Survey = Survey;
}])


.controller('QuestionNodeCtrl', [
        '$scope', 'QuestionNode', 'routeData', 'Editor', 'questionAuthz',
        '$location', 'Notifications', 'Current', 'format', 'Structure',
        'layout', 'Arrays', 'ResponseNode', 'Enqueue', '$timeout', '$route',
        function($scope, QuestionNode, routeData, Editor, authz,
                 $location, Notifications, current, format, Structure,
                 layout, Arrays, ResponseNode, Enqueue, $timeout, $route) {

    // routeData.parent and routeData.survey will only be defined when
    // creating a new qnode.

    $scope.layout = layout;
    $scope.submission = routeData.submission;
    if (routeData.qnode) {
        // Editing old
        $scope.qnode = routeData.qnode;
        $scope.children = routeData.children;
        $scope.measures = routeData.measures;
    } else {
        // Creating new
        $scope.qnode = new QuestionNode({
            'parent': routeData.parent,
            'survey': routeData.survey
        });
        $scope.children = null;
        $scope.measures = null;
    }

    $scope.$watchGroup(['qnode', 'qnode.deleted'], function() {
        $scope.structure = Structure($scope.qnode, $scope.submission);
        $scope.program = $scope.structure.program;
        $scope.edit = Editor('qnode', $scope, {
            parentId: routeData.parent && routeData.parent.id,
            surveyId: routeData.survey && routeData.survey.id,
            programId: $scope.program.id
        });
        if (!$scope.qnode.id)
            $scope.edit.edit();

        var levels = $scope.structure.survey.structure.levels;
        $scope.currentLevel = levels[$scope.structure.qnodes.length - 1];
        $scope.nextLevel = levels[$scope.structure.qnodes.length];

        $scope.checkRole = authz(current, $scope.program, $scope.submission);
        $scope.editable = ($scope.program.isEditable &&
            !$scope.structure.deletedItem &&
            !$scope.submission &&
            $scope.checkRole('program_node_edit'));
    });

    $scope.$on('EditSaved', function(event, model) {
        $location.url(format(
            '/1/qnode/{}?program={}', model.id, $scope.program.id));
    });
    $scope.$on('EditDeleted', function(event, model) {
        if (model.parent) {
            $location.url(format(
                '/1/qnode/{}?program={}', model.parent.id,
                $scope.program.id));
        } else {
            $location.url(format(
                '/1/survey/{}?program={}', model.survey.id,
                $scope.program.id));
        }
    });

    // Used to get history
    $scope.QuestionNode = QuestionNode;

    if ($scope.submission) {
        $scope.rnode = ResponseNode.get({
            submissionId: $scope.submission.id,
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
                        name: 'Draft',
                        value: rnode.nDraft,
                        fraction: rnode.nDraft / $scope.qnode.nMeasures
                    },
                    {
                        name: 'Final',
                        value: rnode.nFinal,
                        fraction: rnode.nFinal / $scope.qnode.nMeasures
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
                    rnode.nFinal >= $scope.qnode.nMeasures ?
                        'final' :
                        'draft',
                relevance: rnode.nNotRelevant >= $scope.qnode.nMeasures ?
                        'RELEVANT' : 'NOT_RELEVANT',
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
                Notifications.set('edit', 'error',
                    "Failed to get response details: " + details.statusText);
                return;
            }
        );

        $scope.saveRnode = function() {
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
        };
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

        $scope.showBulkApproval = false;
        $scope.toggleBulk = function() {
            $scope.showBulkApproval = !$scope.showBulkApproval;
        };
        $scope.showBulkNa = false;
        $scope.toggleBulkNa = function() {
            $scope.showBulkNa = !$scope.showBulkNa;
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

        $scope.relevanceOptions = [{
            name: 'NOT_RELEVANT',
            desc: "Mark all responses as Not Relevant",
        }, {
            name: 'RELEVANT',
            desc: "Mark all responses as Relevant",
        },];

        var bulkAction = function(params) {
            $scope.rnode.$save(params,
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
        $scope.setState = function(approval) {
            var promote;
            if ($scope.stats.promote == 'BOTH')
                promote = ['PROMOTE', 'DEMOTE'];
            else if ($scope.stats.promote == 'PROMOTE')
                promote = ['PROMOTE'];
            else
                promote = ['DEMOTE'];

            bulkAction({
                approval: approval,
                promote: promote,
                missing: $scope.stats.missing,
            });
        };
        $scope.setNotRelevant = function(relevance) {
            bulkAction({
                relevance: relevance,
                missing: $scope.stats.missing,
            });
        };

        $scope.demoStats = [
            {
                name: 'Draft',
                value: 120,
                fraction: 12/12
            },
            {
                name: 'Final',
                value: 100,
                fraction: 10/12
            },
            {
                name: 'Reviewed',
                value: 80,
                fraction: 8/12
            },
            {
                name: 'Approved',
                value: 60,
                fraction: 6/12
            },
        ];
    }

    $scope.getSubmissionUrl = function(submission) {
        if (submission) {
            return format('/1/qnode/{}?submission={}',
                $scope.qnode.id, submission.id);
        } else {
            return format('/1/qnode/{}?program={}',
                $scope.qnode.id, $scope.program.id);
        }
    };
}])


.controller('StatisticsCtrl', [
        '$scope', 'QuestionNode', 'routeData', 'Editor', 'questionAuthz',
        '$location', 'Notifications', 'Current', 'format', 'Structure',
        'layout', 'Arrays', 'ResponseNode', 'Statistics', 'Submission',
        '$timeout',
        function($scope, QuestionNode, routeData, Editor, authz,
                 $location, Notifications, current, format, Structure,
                 layout, Arrays, ResponseNode, Statistics, Submission,
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
    $scope.submission1 = routeData.submission1;
    $scope.submission2 = routeData.submission2;
    $scope.rnodes1 = routeData.rnodes1;
    $scope.rnodes2 = routeData.rnodes2;
    $scope.stats1 = routeData.stats1;
    $scope.stats2 = routeData.stats2;
    $scope.qnode1 = routeData.qnode1;
    $scope.qnode2 = routeData.qnode2;
    $scope.approval = routeData.approval;
    $scope.allowedStates = routeData.approvals;
    $scope.struct1 = Structure(
        routeData.qnode1 || routeData.submission1.survey,
        routeData.submission1);
    if (routeData.submission2) {
        $scope.struct2 = Structure(
            routeData.qnode2 || routeData.submission2.survey,
            routeData.submission2);
    }
    $scope.layout = layout;

    $scope.getSubmissionUrl1 = function(submission) {
        var query;
        if (submission) {
            query = format('submission1={}&submission2={}',
                submission.id,
                $scope.submission2 ? $scope.submission2.id : '');
        } else {
            query = format('submission1={}',
                $scope.submission2 ? $scope.submission2.id : '');
        }
        return format('/1/statistics?{}&qnode={}&approval={}',
            query, $location.search()['qnode'] || '', $scope.approval);
    };
    $scope.getSubmissionUrl2 = function(submission) {
        var query;
        if (submission) {
            query = format('submission1={}&submission2={}',
                $scope.submission1 ? $scope.submission1.id : '',
                submission.id);
        } else {
            query = format('submission1={}',
                $scope.submission1 ? $scope.submission1.id : '');
        }
        return format('/1/statistics?{}&qnode={}&approval={}',
            query, $location.search()['qnode'] || '', $scope.approval);
    };

    $scope.getNavUrl = function(item, key) {
        var aid1 = $scope.submission1.id;
        var aid2 = $scope.submission2 ? $scope.submission2.id : ''
        if (item.path == 'qnode') {
            return format(
                '#/1/statistics?submission1={}&submission2={}&qnode={}&approval={}',
                aid1, aid2, key, $scope.approval);
        } else if (item.path == 'submission') {
            return format(
                '#/1/statistics?submission1={}&submission2={}&approval={}',
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

    var fillData = function(submission, rnodes, stats) {
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

    fillData($scope.submission1, $scope.rnodes1, $scope.stats1);
    if ($scope.submission2)
        fillData($scope.submission2, $scope.rnodes2, $scope.stats2);

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

    if ($scope.submission) {
        $scope.query = 'submission=' + $scope.submission.id;
    } else if ($scope.survey) {
        $scope.query = 'program=' + $scope.program.id;
        $scope.query += '&survey=' + $scope.survey.id;
        $scope.edit.params = {
            programId: $scope.program.id,
            surveyId: $scope.survey.id,
            root: ''
        }
    } else {
        $scope.query = 'program=' + $scope.program.id;
        $scope.edit.params.parentId = $scope.qnode.id;
        $scope.edit.params = {
            programId: $scope.program.id,
            parentId: $scope.qnode.id
        }
    }

    $scope.search = {
        deleted: false
    };
    $scope.$watchGroup(['search.deleted', 'survey.id',
                        'submission.survey.id', 'qnode.id'], function(vars) {
        var deleted = vars[0];
        var hid = vars[1] || vars[2];
        var qid = vars[3];
        if (!hid && !qid)
            return;

        QuestionNode.query({
            parentId: qid,
            surveyId: hid,
            programId: $scope.program.id,
            root: qid ? undefined : '',
            deleted: deleted
        }, function(children) {
            $scope.children = children;
        });
    });

    $scope.$watchGroup(['survey', 'structure'], function(vars) {
        var level;
        if ($scope.submission && !$scope.qnode)
            level = $scope.submission.survey.structure.levels[0];
        else if ($scope.survey)
            level = $scope.survey.structure.levels[0];
        else
            level = $scope.nextLevel;
        $scope.level = level;
    });

    if ($scope.submission) {
        // Get the responses that are associated with this qnode and submission.
        ResponseNode.query({
            submissionId: $scope.submission.id,
            parentId: $scope.qnode ? $scope.qnode.id : null,
            surveyId: $scope.survey ? $scope.survey.id : null,
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
                                name: 'Draft',
                                value: rnode.nDraft,
                                fraction: rnode.nDraft / nm
                            },
                            {
                                name: 'Final',
                                value: rnode.nFinal,
                                fraction: rnode.nFinal / nm
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
                name: 'Draft',
                value: 0,
                fraction: 0
            },
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

    if ($scope.submission) {
        $scope.query = 'submission=' + $scope.submission.id;
    } else {
        $scope.query = 'program=' + $scope.program.id;
        $scope.query += "&parent=" + $scope.qnode.id;
    }

    $scope.edit.params = {
        programId: $scope.program.id,
        qnodeId: $scope.qnode.id
    }

    $scope.level = $scope.structure.survey.structure.measure;

    if ($scope.submission) {
        // Get the responses that are associated with this qnode and submission.
        Response.query({
            submissionId: $scope.submission.id,
            qnodeId: $scope.qnode.id
        }).$promise.then(
            function success(responses) {
                var rmap = {};
                for (var i = 0; i < responses.length; i++) {
                    var r = responses[i];
                    var nApproved = r.approval == 'approved' ? 1 : 0;
                    var nReviewed = r.approval == 'reviewed' ? 1 : nApproved;
                    var nFinal = r.approval == 'final' ? 1 : nReviewed;
                    var nDraft = r.approval == 'draft' ? 1 : nFinal;
                    rmap[r.measure.id] = {
                        score: r.score,
                        notRelevant: r.notRelevant,
                        progressItems: [
                            {
                                name: 'Draft',
                                value: nDraft,
                                fraction: nDraft
                            },
                            {
                                name: 'Final',
                                value: nFinal,
                                fraction: nFinal
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
                name: 'Draft',
                value: 0,
                fraction: 0
            },
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

    $scope.survey1 = routeData.survey1;
    $scope.survey2 = routeData.survey2;
    $scope.program1 = $scope.survey1.program;
    $scope.program2 = $scope.survey2.program;

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
            programId1: $scope.program1.id,
            programId2: $scope.program2.id,
            surveyId: $scope.survey1.id,
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

    $scope.getItemUrl = function(item, entity, program) {
        if (item.type == 'qnode')
            return format("/1/qnode/{}?program={}", entity.id, program.id);
        else if (item.type == 'measure')
            return format("/1/measure/{}?program={}&parent={}",
                entity.id, program.id, entity.parentId);
        else if (item.type == 'program')
            return format("/1/program/{}", program.id);
        else if (item.type == 'survey')
            return format("/1/survey/{}?program={}", entity.id, program.id);
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
    $scope.survey = routeData.survey;
    $scope.parent = routeData.parent;
    $scope.program = routeData.program;

    $scope.qnode = {
        obType: 'qnode',
        survey: $scope.parent ? $scope.parent.survey : $scope.survey,
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
            programId: $scope.program.id
        }, postData,
            function success(measure, headers) {
                var message = "Saved";
                if (headers('Operation-Details'))
                    message += ': ' + headers('Operation-Details');
                Notifications.set('edit', 'success', message);
                $location.url(format(
                    '/1/qnode/{}?program={}', $scope.parent.id, $scope.program.id));
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
        programId: $scope.program.id,
        surveyId: $scope.structure.survey.id,
        desc: true,
        page: 0,
        pageSize: 10
    };
    $scope.$watch('search', function(search) {
        QuestionNode.query(search).$promise.then(function(qnodes) {
            $scope.qnodes = qnodes;
        });
    }, true);

    $scope.checkRole = authz(current, $scope.program);
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
    $scope.program = routeData.program;

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
            programId: $scope.program.id
        }, postData,
            function success(measure, headers) {
                var message = "Saved";
                if (headers('Operation-Details'))
                    message += ': ' + headers('Operation-Details');
                Notifications.set('edit', 'success', message);
                $location.url(format(
                    '/1/qnode/{}?program={}', $scope.qnode.id, $scope.program.id));
            },
            function failure(details) {
                Notifications.set('edit', 'error',
                    "Could not save object: " + details.statusText);
            }
        );
    };

    $scope.search = {
        term: "",
        programId: $scope.program.id,
        page: 0,
        pageSize: 10
    };
    $scope.$watch('search', function(search) {
        Measure.query(search).$promise.then(function(measures) {
            $scope.measures = measures;
        });
    }, true);

    $scope.checkRole = authz(current, $scope.program);
    $scope.QuestionNode = QuestionNode;
    $scope.Measure = Measure;
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

    var dropzone = new Dropzone("#dropzone", config);

    $scope.save = function() {
        $scope.upload();
        if ($scope.externals.length > 0) {
            Attachment.saveExternals({
                submissionId: $scope.submission.id,
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
            dropzone.options.url = '/submission/' + $scope.submission.id +
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
            submissionId: $scope.submission.id,
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


/**
 * Drop-down menu to navigate to old versions of an entity.
 */
.controller('ResponseHistory', ['$scope', '$location', 'Response',
        'Notifications',
        function($scope, $location, Response, Notifications) {
    $scope.toggled = function(open) {
        if (open) {
            $scope.search = {
                submissionId: $scope.submission.id,
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
            submissionId: $scope.submission.id,
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
