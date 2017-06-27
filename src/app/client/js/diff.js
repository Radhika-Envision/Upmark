'use strict'

angular.module('upmark.diff', [
    'ngResource', 'upmark.admin', 'upmark.surveyQuestions'])


.factory('Diff', ['$resource', function($resource) {
    return $resource('/report/diff.json', {}, {
        get: { method: 'GET', isArray: false, cache: false }
    });
}])


.controller('DiffCtrl', [
        '$scope', 'QuestionNode', 'routeData', 'Editor',
        '$location', 'Notifications', 'Current', 'format', 'Structure',
        'Enqueue', 'Diff', '$timeout',
        function($scope, QuestionNode, routeData, Editor,
                 $location, Notifications, current, format, Structure,
                 Enqueue, Diff, $timeout) {

    $scope.survey1 = routeData.survey1;
    $scope.survey2 = routeData.survey2;
    $scope.program1 = $scope.survey1.program;
    $scope.program2 = $scope.survey2.program;

    $scope.diff = null;

    $scope.tags = [
        'context', 'added', 'deleted', 'modified',
        'reordered', 'relocated', 'list index'];

    $scope.updateTags = function() {
        var ignoreTags = $location.search()['ignoreTags'];
        if (angular.isString(ignoreTags))
            ignoreTags = [ignoreTags];
        else if (ignoreTags == null)
            ignoreTags = [];
        $scope.ignoreTags = ignoreTags;
    };
    $scope.update = Enqueue(function() {
        $scope.longRunning = false;
        $scope.diff = Diff.get({
            programId1: $scope.program1.id,
            programId2: $scope.program2.id,
            surveyId: $scope.survey1.id,
            ignoreTag: $scope.ignoreTags
        });
        $timeout(function() {
            $scope.longRunning = true;
        }, 5000);
    }, 1000, $scope);
    $scope.$on('$routeUpdate', function(scope, next, current) {
        $scope.updateTags();
        $scope.update();
    });
    $scope.updateTags();
    $scope.update();

    $scope.toggleTag = function(tag) {
        var i = $scope.ignoreTags.indexOf(tag);
        if (i >= 0)
            $scope.ignoreTags.splice(i, 1);
        else
            $scope.ignoreTags.push(tag);
        $location.search('ignoreTags', $scope.ignoreTags);
    };
    $scope.tagEnabled = function(tag) {
        return $scope.ignoreTags.indexOf(tag) < 0;
    };

    $scope.getItemUrl = function(item, entity, program) {
        if (item.type == 'qnode')
            return format("/2/qnode/{}?program={}", entity.id, program.id);
        else if (item.type == 'measure')
            return format("/2/measure/{}?program={}&survey={}",
                entity.id, program.id, entity.surveyId);
        else if (item.type == 'program')
            return format("/2/program/{}", program.id);
        else if (item.type == 'survey')
            return format("/2/survey/{}?program={}", entity.id, program.id);
    };

    $scope.chooser = false;
    $scope.toggleDropdown = function(num) {
        if ($scope.chooser == num)
            $scope.chooser = null;
        else
            $scope.chooser = num;
    };

}])


;
