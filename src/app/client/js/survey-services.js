'use strict';

angular.module('upmark.survey.services', [
    'ngResource', 'vpac.utils'])


.factory('Diff', ['$resource', function($resource) {
    return $resource('/report/diff.json', {}, {
        get: { method: 'GET', isArray: false, cache: false }
    });
}])


;
