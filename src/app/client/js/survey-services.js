'use strict';

angular.module('upmark.survey.services', [
    'ngResource', 'vpac.utils'])


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
