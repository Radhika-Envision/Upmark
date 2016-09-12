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
    return $resource('/measure/:id.json', {id: '@id'}, {
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
    return $resource('/response_type/:id.json', {id: '@id'}, {
        get: { method: 'GET', cache: false },
        create: { method: 'POST' },
        save: { method: 'PUT' },
        query: {
            method: 'GET', isArray: true, cache: false,
            interceptor: {response: paged}
        },
    });
}])


.factory('Attachment', ['$resource', function($resource) {
    return $resource('/submission/:submissionId/measure/:measureId/attachment.json',
            {submissionId: '@submissionId', measureId: '@measureId'}, {
        saveExternals: { method: 'PUT', isArray: true },
        query: { method: 'GET', isArray: true, cache: false },
        remove: { method: 'DELETE', url: '/attachment/:id.json', cache: false }
    });
}])


.factory('Statistics', ['$resource', function($resource) {
    return $resource('/statistics/program/:programId/survey/:surveyId.json', {
        programId: '@programId',
        surveyId: '@surveyId',
    }, {
        get: { method: 'GET', isArray: true, cache: false }
    });
}])


.factory('Diff', ['$resource', function($resource) {
    return $resource('/diff.json', {}, {
        get: { method: 'GET', isArray: false, cache: false }
    });
}])


;
