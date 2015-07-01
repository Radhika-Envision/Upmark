'use strict';

angular.module('wsaa.surveyQuestions', [
    'ngResource', 'ngSanitize', 'ui.select', 'wsaa.admin'])


.factory('Survey', ['$resource', function($resource) {
    return $resource('/survey/:id.json', {id: '@id'}, {
        get: { method: 'GET', cache: false },
        save: { method: 'PUT' },
        query: { method: 'GET', url: '/survey.json', isArray: true,
            cache: false },
        create: { method: 'POST', url: '/survey.json' }
    });
}])


// 'Func' because 'function' is a reserved word
.factory('Func', ['$resource', function($resource) {
    return $resource('/function/:id.json', {id: '@id'}, {
        get: { method: 'GET', cache: false },
        save: { method: 'PUT' },
        query: { method: 'GET', url: '/function.json', isArray: true,
            cache: false },
        create: { method: 'POST', url: '/function.json' }
    });
}])


.factory('Process', ['$resource', function($resource) {
    return $resource('/process/:id.json', {id: '@id'}, {
        get: { method: 'GET', cache: false },
        save: { method: 'PUT' },
        query: { method: 'GET', url: '/process.json', isArray: true,
            cache: false },
        create: { method: 'POST', url: '/process.json' }
    });
}])


.factory('SubProcess', ['$resource', function($resource) {
    return $resource('/subprocess/:id.json', {id: '@id'}, {
        get: { method: 'GET', cache: false },
        save: { method: 'PUT' },
        query: { method: 'GET', url: '/subprocess.json', isArray: true,
            cache: false },
        create: { method: 'POST', url: '/subprocess.json' }
    });
}])


.factory('Measure', ['$resource', function($resource) {
    return $resource('/measure/:id.json', {id: '@id'}, {
        get: { method: 'GET', cache: false },
        save: { method: 'PUT' },
        query: { method: 'GET', url: '/measure.json', isArray: true,
            cache: false },
        create: { method: 'POST', url: '/measure.json' }
    });
}])


.factory('questionAuthz', ['Roles', function(Roles) {
    return function(current, user) {
        return function(functionName) {
            return Roles.hasPermission(current.user.role, 'author');
        };
    };
}])


.controller('SurveyCtrl', [
        '$scope', 'Survey', 'routeData', 'Editor', 'questionAuthz',
        '$location', 'Notifications', 'Current',
        function($scope, Survey, routeData, Editor, authz,
                 $location, Notifications, current) {

    $scope.current = routeData.current;
    $scope.edit = Editor(Survey, 'survey', $scope);
    if (routeData.survey) {
        // Editing old
        $scope.survey = routeData.survey;
    } else {
        // Creating new
        $scope.survey = new Survey({});
        $scope.edit.edit();
    }

    $scope.$on('EditSaved', function(event, model) {
        $location.url('/survey/' + model.id);
    });

    $scope.checkRole = authz(current, $scope.survey);
}])


.controller('SurveyListCtrl', ['$scope', 'questionAuthz', 'Survey', 'Current',
        function($scope, authz, Survey, current) {

    $scope.checkRole = authz(current, null);

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

;
