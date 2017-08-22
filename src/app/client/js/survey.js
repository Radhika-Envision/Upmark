'use strict'

angular.module('upmark.survey', [
    'upmark.structure'])


.directive('questionHeader', [function() {
    return {
        restrict: 'E',
        scope: {
            entity: '=',
            submission: '=',
            getUrl: '='
        },
        replace: true,
        templateUrl: 'question_header.html',
        controller: ['$scope', 'layout', 'Program', 'Structure', 'hotkeys', 'format',
                '$location', 'currentUser',
                function($scope, layout, Program, Structure, hotkeys, format, $location, currentUser) {
            $scope.layout = layout;
            $scope.currentSurveyGroup = null;
            $scope.$watchGroup(['entity', 'submission'], function(vals) {
                $scope.structure = Structure(vals[0], vals[1]);
                $scope.currentItem = $scope.structure.hstack[
                    $scope.structure.hstack.length - 1];
                $scope.upItem = $scope.structure.hstack[
                    $scope.structure.hstack.length - 2];
            });

            $scope.setSurveyGroup = function() {
                if (!$scope.structure)
                    return

                let program = $scope.structure.hstack[0];
                Program.get({id: program.entity.id}).$promise.then(
                    function(program) {
                        for (let i = 0, nPsg = program.surveygroups.length; i < nPsg; i++) {
                            let psg_id = program.surveygroups[i].id;
                            for (let j = 0, nUsg = currentUser.surveygroups.length; j < nUsg; j++) {
                                let usg_id = currentUser.surveygroups[j].id;
                                if (usg_id == psg_id) {
                                    $scope.currentSurveyGroup = program.surveygroups[i];
                                    break
                                }
                            }
                            if ($scope.currentSurveyGroup)
                                break
                            i++;
                        }
                    });
            };

            $scope.itemUrl = function(item, accessor) {
                if (!item)
                    return "";

                var accessor = accessor || 'id';
                var key = item.entity[accessor];

                if (!key)
                    return "";

                if ($scope.getUrl) {
                    var url = $scope.getUrl(item, key);
                    if (url)
                        return url;
                }

                var path = format("#/3/{}/{}", item.path, key);
                var query = [];
                if (item.path == 'program' || item.path == 'submission') {
                } else if (item.path == 'survey') {
                    query.push('program=' + $scope.structure.program.id);
                } else {
                    if ($scope.submission)
                        query.push('submission=' + $scope.submission.id);
                    else
                        query.push('program=' + $scope.structure.program.id);
                }
                if (item.path == 'measure' && !$scope.submission) {
                    query.push('survey=' + $scope.structure.survey.id);
                }
                url = path + '?' + query.join('&');

                return url;
            };

            hotkeys.bindTo($scope)
                .add({
                    combo: ['u'],
                    description: "Go up one level of the survey",
                    callback: function(event, hotkey) {
                        var url = $scope.itemUrl($scope.upItem);
                        if (!url)
                            url = '/3/programs';
                        $location.url(url.substring(1));
                    }
                })
                .add({
                    combo: ['p'],
                    description: "Go to the previous category or measure",
                    callback: function(event, hotkey) {
                        var url = $scope.itemUrl($scope.currentItem, 'prev');
                        if (!url)
                            return;
                        $location.url(url.substring(1));
                    }
                })
                .add({
                    combo: ['n'],
                    description: "Go to the next category or measure",
                    callback: function(event, hotkey) {
                        var url = $scope.itemUrl($scope.currentItem, 'next');
                        if (!url)
                            return;
                        $location.url(url.substring(1));
                    }
                });

            $scope.$watch('structure', function(){
                $scope.currentSurveyGroup = null;
                $scope.setSurveyGroup()
            })
        }]
    }
}])


;
