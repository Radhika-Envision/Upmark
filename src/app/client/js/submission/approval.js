'use strict'

angular.module('upmark.submission.approval', [])


.directive('approval', [function() {
    return {
        restrict: 'E',
        scope: {
            model: '='
        },
        template: '<i class="boxed" ng-class="cls" title="{{model}}">' +
                    '{{initial}}</i>',
        replace: true,
        controller: ['$scope', function($scope) {
            $scope.$watch('model', function(approval) {
                $scope.initial = approval[0].toUpperCase();
                switch (approval) {
                case 'draft':
                    $scope.initial = 'D';
                    $scope.cls = 'aq-1';
                    break;
                case 'final':
                    $scope.initial = 'F';
                    $scope.cls = 'aq-2';
                    break;
                case 'reviewed':
                    $scope.initial = 'R';
                    $scope.cls = 'aq-3';
                    break;
                case 'approved':
                    $scope.initial = 'A';
                    $scope.cls = 'aq-4';
                    break;
                }
            });
        }]
    };
}])


.directive('approvalButtons', function(bind) {
    return {
        restrict: 'E',
        templateUrl: 'approval_buttons.html',
        scope: {
            model: '=',
            allowed: '=',
            mode: '=',
            setState: '&',
        },
        controller: function($scope) {
            $scope.m = {};
            bind($scope, 'm.model', $scope, 'model', true);
            $scope.isAllowed = function(value) {
                if (!$scope.allowed)
                    return true;
                return $scope.allowed.indexOf(value) >= 0;
            };
            $scope.setValue = function(value, $event) {
                $scope.setState({state: value, $event: $event});
            };
        },
    };
})
