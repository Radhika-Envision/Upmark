'use strict';

angular.module('upmark.survey.services', [
    'ngResource', 'vpac.utils'])


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


.factory('Statistics', ['$resource', function($resource) {
    return $resource('/report/sub/stats/program/:programId/survey/:surveyId.json', {
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
