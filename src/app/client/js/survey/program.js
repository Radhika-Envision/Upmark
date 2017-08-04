'use strict';

angular.module('upmark.survey.program',[
    'ngResource', 'ngSanitize', 'ui.select', 'ui.sortable',
    'upmark.admin.settings', 'upmark.user', 'upmark.chain'])


.config(function($routeProvider, chainProvider) {
    $routeProvider
        .when('/:uv/programs', {
            templateUrl : 'program_list.html',
            controller : 'ProgramListCtrl'
        })
        .when('/:uv/program/new', {
            templateUrl : 'program.html',
            controller : 'ProgramCtrl',
            resolve: {routeData: chainProvider({
                duplicate: ['Program', '$route', function(Program, $route) {
                    if (!$route.current.params.duplicate)
                        return null;
                    return Program.get({
                        id: $route.current.params.duplicate
                    }).$promise;
                }]
            })}
        })
        .when('/:uv/program/import', {
            templateUrl : 'program_import.html',
            controller : 'ProgramImportCtrl'
        })
        .when('/:uv/program/:program', {
            templateUrl : 'program.html',
            controller : 'ProgramCtrl',
            resolve: {routeData: chainProvider({
                program: ['Program', '$route', function(Program, $route) {
                    return Program.get({
                        id: $route.current.params.program
                    }).$promise;
                }]
            })}
        })
    ;
})


.factory('Program', ['$resource', 'paged', function($resource, paged) {
    return $resource('/program/:id.json', {id: '@id'}, {
        get: { method: 'GET', cache: false },
        create: { method: 'POST' },
        save: { method: 'PUT' },
        query: {
            method: 'GET', isArray: true, cache: false,
            interceptor: {response: paged}
        },
        history: { method: 'GET', url: '/program/:id/history.json',
            isArray: true, cache: false }
    });
}])


.controller('ProgramCtrl', function(
        $scope, Program, routeData, Editor, Authz, hotkeys,
        $location, Notifications, Survey, layout, format,
        Organisation, Submission, currentUser, SurveyGroup) {

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
            obType: 'program',
            responseTypes: [],
            surveygroups: angular.copy(currentUser.surveygroups),
        });
        $scope.surveys = null;
        $scope.edit.edit();
        $scope.duplicating = false;
    }

    $scope.$on('EditSaved', function(event, model) {
        $location.url('/2/program/' + model.id);
    });
    $scope.$on('EditDeleted', function(event, model) {
        $location.url('/2/programs');
    });

    $scope.checkRole = Authz({program: $scope.program});

    $scope.toggleEditable = function() {
        $scope.program.$save({editable: !$scope.program.isEditable},
            function success() {
                Notifications.set('edit', 'success', "Saved", 5000);
            },
            function failure(details) {
                Notifications.set('edit', 'error',
                    "Could not save: " + details.statusText);
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
            deleted: $scope.search.deleted,
            organisationId: currentUser.organisation.id,
        }, function success(surveys) {
            $scope.surveys = surveys
        }, function failure(details) {
                Notifications.set('edit', 'error',
                    "Could not get list of surveys: " + details.statusText);
        });
    });

    $scope.$watch('surveys', function(surveys) {
        if (!surveys) {
            $scope.nLocked = 0;
            return;
        }
        $scope.nLocked = surveys.filter(function(survey) {
            return !survey.purchased;
        }).length;
        console.log($scope.nLocked)
    });

    $scope.deleteSurveygroup = function(i) {
        $scope.edit.model.surveygroups.splice(i, 1);
    };

    $scope.searchSurveygroup = function(term) {
        return SurveyGroup.query({term: term}).$promise;
    };

    $scope.Program = Program;

    hotkeys.bindTo($scope)
        .add({
            combo: ['a'],
            description: "Add a new question set",
            callback: function(event, hotkey) {
                $location.url(
                    format("/2/survey/new?program={{}}", $scope.program.id));
            }
        })
        .add({
            combo: ['s'],
            description: "Search for measures",
            callback: function(event, hotkey) {
                $location.url(
                    format("/2/measures?program={{}}", $scope.program.id));
            }
        });
})


.controller('ProgramListCtrl', function($scope, Authz, Program, layout) {

    $scope.layout = layout;
    $scope.checkRole = Authz({});

    $scope.search = {
        term: "",
        editable: null,
        deleted: false,
        page: 0,
        pageSize: 10
    };
    $scope.$watch('search', function(search) {
        Program.query(search).$promise.then(function(programs) {
            $scope.programs = programs;
        });
    }, true);
})


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
            $location.url('/2/program/' + response);
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
                    $location.url('/2/program/' + program.id);
                else
                    $location.search('program', program.id);
            };
            $scope.isActive = function(program) {
                if ($scope.entity == $scope.structure.program)
                    return $location.url().indexOf('/2/program/' + program.id) >= 0;
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
                    '/2/diff/{}/{}/{}?ignoreTags=list+index',
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
