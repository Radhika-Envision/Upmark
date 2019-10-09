'use strict'

angular.module('upmark.location', [
    'ngResource'])


.factory('LocationSearch', ['$resource', function($resource) {
    return $resource('/geo/:term.json', {}, {
        get: { method: 'GET', cache: false },
    });
}])


;
