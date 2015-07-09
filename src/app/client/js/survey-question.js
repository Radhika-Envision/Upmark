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


// 'Func' because 'function' is a reserved word
.factory('Func', ['$resource', function($resource) {
    return $resource('/function/:id.json', {id: '@id'}, {
        get: { method: 'GET', cache: false },
        create: { method: 'POST' },
        save: { method: 'PUT' },
        query: { method: 'GET', isArray: true, cache: false },
        reorder: { method: 'PUT', isArray: true }
    });
}])


.factory('Process', ['$resource', function($resource) {
    return $resource('/process/:id.json', {id: '@id'}, {
        get: { method: 'GET', cache: false },
        create: { method: 'POST' },
        save: { method: 'PUT' },
        query: { method: 'GET', isArray: true, cache: false },
        reorder: { method: 'PUT', isArray: true }
    });
}])


.factory('SubProcess', ['$resource', function($resource) {
    return $resource('/subprocess/:id.json', {id: '@id'}, {
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
        '$location', 'Notifications', 'Current', 'Func',
        function($scope, Survey, routeData, Editor, authz,
                 $location, Notifications, current, Func) {

    $scope.edit = Editor('survey', $scope);
    if (routeData.survey) {
        // Viewing old
        $scope.survey = routeData.survey;
        $scope.funcs = routeData.funcs;
    } else {
        // Creating new
        $scope.survey = new Survey({});
        $scope.funcs = null;
        $scope.edit.edit();
    }

    $scope.$on('EditSaved', function(event, model) {
        $location.url('/survey/' + model.id);
    });

    $scope.checkRole = authz(current, $scope.survey);
    $scope.Func = Func;
}])


.controller('SurveyListCtrl', ['$scope', 'questionAuthz', 'Survey', 'Current',
        function($scope, authz, Survey, current) {

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
            entity: '='
        },
        replace: true,
        templateUrl: 'question_header.html',
        controller: ['$scope', function($scope) {
            $scope.$watchGroup([
                    'entity.survey', 'entity.function',
                    'entity.process', 'entity.subProcess'],
                function(vars) {
                    var type;
                    if (vars[3]) {
                        type = 'measure';
                    } else if (vars[2]) {
                        type = 'subProcess';
                    } else if (vars[1]) {
                        type = 'process';
                    } else if (vars[0]) {
                        type = 'func';
                    } else {
                        type = 'survey';
                    }

                    var hstack = [];
                    var entity = $scope.entity;
                    switch (type) {
                    case 'measure':
                        hstack.push({
                            type: 'measure',
                            label: 'M',
                            entity: entity
                        });
                        entity = entity.subProcess;
                    case 'subProcess':
                        hstack.push({
                            type: 'subprocess',
                            label: 'Sp',
                            entity: entity
                        });
                        entity = entity.process;
                    case 'process':
                        hstack.push({
                            type: 'process',
                            label: 'P',
                            entity: entity
                        });
                        entity = entity['function'];
                    case 'func':
                        hstack.push({
                            type: 'function',
                            label: 'F',
                            entity: entity
                        });
                        entity = entity.survey;
                    case 'survey':
                        hstack.push({
                            type: 'survey',
                            label: 'S',
                            entity: entity
                        });
                        $scope.survey = entity;
                    }
                    hstack.reverse();
                    $scope.hstack = hstack;
            });
        }]
    }
}])


.controller('FuncCtrl', [
        '$scope', 'Func', 'routeData', 'Editor', 'questionAuthz',
        '$location', 'Notifications', 'Current', 'Survey', 'format', 'Process',
        function($scope, Func, routeData, Editor, authz,
                 $location, Notifications, current, Survey, format, Process) {

    $scope.survey = routeData.survey;
    $scope.edit = Editor('func', $scope, {surveyId: $scope.survey.id});
    if (routeData.func) {
        // Editing old
        $scope.func = routeData.func;
        $scope.procs = routeData.procs;
    } else {
        // Creating new
        $scope.func = new Func({
            survey: $scope.survey
        });
        $scope.procs = null;
        $scope.edit.edit();
    }

    $scope.$on('EditSaved', function(event, model) {
        $location.url(format(
            '/function/{}?survey={}', model.id, $scope.survey.id));
    });

    $scope.checkRole = authz(current, $scope.survey);
    $scope.Process = Process;
}])


.controller('ProcessCtrl', [
        '$scope', 'Process', 'routeData', 'Editor', 'questionAuthz',
        '$location', 'Notifications', 'Current', 'Survey', 'format',
        'SubProcess',
        function($scope, Process, routeData, Editor, authz,
                 $location, Notifications, current, Survey, format,
                 SubProcess) {

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

    $scope.checkRole = authz(current, $scope.survey);
    $scope.SubProcess = SubProcess;
}])


.controller('SubProcessCtrl', [
        '$scope', 'SubProcess', 'routeData', 'Editor', 'questionAuthz',
        '$location', 'Notifications', 'Current', 'Survey', 'format', 'Measure',
        function($scope, SubProcess, routeData, Editor, authz,
                 $location, Notifications, current, Survey, format, Measure) {

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
            'process': $scope.process
        });
        $scope.measures = null;
        $scope.edit.edit();
    }

    $scope.$on('EditSaved', function(event, model) {
        $location.url(format(
            '/subprocess/{}?survey={}', model.id, $scope.survey.id));
    });

    $scope.checkRole = authz(current, $scope.survey);
    $scope.Measure = Measure;
}])


.controller('MeasureCtrl', [
        '$scope', 'Measure', 'routeData', 'Editor', 'questionAuthz',
        '$location', 'Notifications', 'Current', 'Survey', 'format',
        function($scope, Measure, routeData, Editor, authz,
                 $location, Notifications, current, Survey, format) {

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
            'subprocess': $scope.subprocess
        });
        $scope.edit.edit();
    }

    $scope.$on('EditSaved', function(event, model) {
        $location.url(format(
            '/measure/{}?survey={}', model.id, $scope.survey.id));
    });

    $scope.checkRole = authz(current, $scope.survey);
}])


.controller('CategoryCtrl', ['$scope', '$routeParams', 'routeData', 'format', 'hotkeys', 'Func', '$location', '$timeout',
        function($scope, $routeParams, routeData, format, hotkeys, Func, $location, $timeout) {

    $scope.functions = routeData.functions;
    
    $scope.addFunction = function() {
      var functionTitle = document.getElementById("funcTitle").value;
      if (functionTitle.length > 0) {
        Func.create({
          title: functionTitle,
          description: functionTitle,
          seq: 1
        });
        document.getElementById("funcTitle").value = '';
      }
    };

    $scope.editFunction = function(func) {
      func.editing = true;
    };

    $scope.cancelEditingFunction = function(func) {
      func.editing = false;
    };

    $scope.saveFunction = function(func) {
      func.save();
    };

    $scope.removeFunction = function(func) {
      if (window.confirm('Are you sure to remove this function?')) {
        func.destroy();
      }
    };

    $scope.saveGroups = function() {
      for (var i = $scope.groups.length - 1; i >= 0; i--) {
        var group = $scope.groups[i];
        group.sortOrder = i + 1;
        group.save();
      }
    };

}])


;
