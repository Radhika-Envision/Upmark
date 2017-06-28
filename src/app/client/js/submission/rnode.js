'use strict'

angular.module('upmark.submission.rnode', [
    'ngResource'])


.factory('ResponseNode', ['$resource', function($resource) {
    return $resource('/submission/:submissionId/rnode/:qnodeId.json',
            {submissionId: '@submissionId', qnodeId: '@qnodeId'}, {
        get: { method: 'GET', cache: false },
        save: { method: 'PUT' },
        query: { method: 'GET', isArray: true, cache: false }
    });
}])
