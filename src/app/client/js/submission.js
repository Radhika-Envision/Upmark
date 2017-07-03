'use strict'

angular.module('upmark.submission', [
    ])


.directive('submissionHeader', [function() {
    return {
        templateUrl: 'submission_header.html',
        replace: true,
        scope: true,
        controller: ['$scope', function($scope) {
            $scope.showSubmissionChooser = false;
            $scope.toggleDropdown = function() {
                $scope.showSubmissionChooser = !$scope.showSubmissionChooser;
            };
        }]
    }
}])


;
