'use strict'

angular.module('upmark.notifications', [])


.directive('errorHeader', function() {
    return {
        restrict: 'A',
        scope: {
            errorNode: '=',
        },
        templateUrl: '/error_header.html',
        link: function(scope, elem, attrs) {
            elem.addClass('subheader bg-warning');
            scope.$watch('errorNode.error', function(error) {
                elem.toggleClass('ng-hide', !error);
            });
        }
    };
})


;
