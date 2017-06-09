'use strict';

angular.module('wsaa.survey.services', [
    'ngResource', 'vpac.utils'])


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


.factory('Survey', ['$resource', function($resource) {
    return $resource('/survey/:id.json', {id: '@id'}, {
        get: { method: 'GET', cache: false },
        create: { method: 'POST' },
        save: { method: 'PUT' },
        query: { method: 'GET', isArray: true, cache: false },
        history: { method: 'GET', url: '/survey/:id/program.json',
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
        history: { method: 'GET', url: '/qnode/:id/program.json',
            isArray: true, cache: false }
    });
}])


.factory('Measure', ['$resource', 'paged', function($resource, paged) {
    return $resource('/measure/:id.json?surveyId=:surveyId', {id: '@id'}, {
        get: { method: 'GET', cache: false },
        create: { method: 'POST' },
        save: { method: 'PUT' },
        query: {
            method: 'GET', isArray: true, cache: false,
            interceptor: {response: paged}
        },
        reorder: { method: 'PUT', isArray: true },
        history: { method: 'GET', url: '/measure/:id/program.json',
            isArray: true, cache: false }
    });
}])


.factory('ResponseType', ['$resource', 'paged', function($resource, paged) {
    var ResponseType = $resource('/response_type/:id.json', {
        id: '@id', programId: '@programId'
    }, {
        get: {
            method: 'GET', cache: false,
            interceptor: {response: function(response) {
                response.resource.title = response.resource.name;
                return response.resource;
            }}
        },
        create: { method: 'POST' },
        save: { method: 'PUT' },
        query: {
            method: 'GET', isArray: true, cache: false,
            interceptor: {response: paged}
        },
        history: { method: 'GET', url: '/response_type/:id/program.json',
            isArray: true, cache: false }
    });
    ResponseType.prototype.$createOrSave = function(parameters, success, error) {
        if (!this.id)
            return this.$create(parameters, success, error);
        else
            return this.$save(parameters, success, error);
    };
    return ResponseType;
}])


.factory('Attachment', ['$resource', function($resource) {
    return $resource('/submission/:submissionId/measure/:measureId/attachment.json',
            {submissionId: '@submissionId', measureId: '@measureId'}, {
        saveExternals: { method: 'PUT', isArray: true },
        query: { method: 'GET', isArray: true, cache: false },
        remove: { method: 'DELETE', url: '/attachment/:id', cache: false }
    });
}])


.factory('Statistics', ['$resource', function($resource) {
    return $resource('/report/sub_stats/program/:programId/survey/:surveyId.json', {
        programId: '@programId',
        surveyId: '@surveyId',
    }, {
        get: { method: 'GET', isArray: true, cache: false }
    });
}])


.factory('Diff', ['$resource', function($resource) {
    return $resource('/report/diff.json', {}, {
        get: { method: 'GET', isArray: false, cache: false }
    });
}])


;
