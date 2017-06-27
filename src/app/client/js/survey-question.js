'use strict';

angular.module('upmark.surveyQuestions', [
    'ngResource', 'ngSanitize',
    'ui.select', 'ui.sortable',
    'upmark.admin', 'upmark.survey.services'])


.factory('Structure', function() {
    return function(entity, submission) {
        var stack = [];
        while (entity) {
            stack.push(entity);
            if (entity.obType == 'measure')
                entity = entity.parent || entity.program;
            else if (entity.obType == 'response_type')
                entity = entity.program;
            else if (entity.obType == 'qnode')
                entity = entity.parent || entity.survey;
            else if (entity.obType == 'submission')
                entity = entity.survey;
            else if (entity.obType == 'survey')
                entity = entity.program;
            else if (entity.obType == 'program')
                entity = null;
            else
                entity = null;
        }
        stack.reverse();

        var hstack = [];
        var program = null;
        var survey = null;
        var measure = null;
        var responseType = null;
        // Program
        if (stack.length > 0) {
            program = stack[0];
            hstack.push({
                path: 'program',
                title: 'Program',
                label: 'Pg',
                entity: program,
                level: 's'
            });
        }
        // Survey, or orphaned measure
        if (stack.length > 1) {
            if (stack[1].obType == 'measure') {
                measure = stack[1];
                hstack.push({
                    path: 'measure',
                    title: 'Measures',
                    label: 'M',
                    entity: measure,
                    level: 'm'
                });
            } else if (stack[1].obType == 'response_type') {
                responseType = stack[1];
                hstack.push({
                    path: 'response-type',
                    title: 'Response Types',
                    label: 'RT',
                    entity: responseType,
                    level: 't'
                });
            } else {
                survey = stack[1];
                hstack.push({
                    path: 'survey',
                    title: 'Surveys',
                    label: 'Sv',
                    entity: survey,
                    level: 'h'
                });
            }
        }

        if (submission) {
            // Submissions (when explicitly provided) slot in after survey.
            hstack.splice(2, 0, {
                path: 'submission',
                title: 'Submissions',
                label: 'Sb',
                entity: submission,
                level: 'h'
            });
        }

        var qnodes = [];
        if (stack.length > 2 && survey) {
            var qnodeMaxIndex = stack.length - 1;
            if (stack[stack.length - 1].obType == 'measure') {
                measure = stack[stack.length - 1];
                qnodeMaxIndex = stack.length - 2;
            } else {
                measure = null;
                qnodeMaxIndex = stack.length - 1;
            }

            var structure = survey.structure;
            var lineage = "";
            // Qnodes and measures
            for (var i = 2; i <= qnodeMaxIndex; i++) {
                entity = stack[i];
                var level = structure.levels[i - 2];
                if (entity.seq != null)
                    lineage += "" + (entity.seq + 1) + ".";
                else
                    lineage += "-.";
                hstack.push({
                    path: 'qnode',
                    title: level.title,
                    label: level.label,
                    entity: entity,
                    level: i - 2,
                    lineage: lineage
                });
                qnodes.push(entity);
            }

            if (measure) {
                if (measure.seq != null)
                    lineage += "" + (measure.seq + 1) + ".";
                else
                    lineage += "-.";
                hstack.push({
                    path: 'measure',
                    title: structure.measure.title,
                    label: structure.measure.label,
                    entity: measure,
                    level: 'm',
                    lineage: lineage
                });
            }
        }

        var deletedItem = null;
        for (var i = 0; i < hstack.length; i++) {
            var item = hstack[i];
            if (item.entity.deleted)
                deletedItem = item;
        }

        return {
            program: program,
            survey: survey,
            submission: submission,
            qnodes: qnodes,
            measure: measure,
            responseType: responseType,
            hstack: hstack,
            deletedItem: deletedItem
        };
    };
})


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
        controller: ['$scope', 'layout', 'Structure', 'hotkeys', 'format',
                '$location',
                function($scope, layout, Structure, hotkeys, format, $location) {
            $scope.layout = layout;
            $scope.$watchGroup(['entity', 'submission'], function(vals) {
                $scope.structure = Structure(vals[0], vals[1]);
                $scope.currentItem = $scope.structure.hstack[
                    $scope.structure.hstack.length - 1];
                $scope.upItem = $scope.structure.hstack[
                    $scope.structure.hstack.length - 2];
            });

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

                var path = format("#/2/{}/{}", item.path, key);
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
                            url = '/2/programs';
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
        }]
    }
}])


.controller('MeasureLinkCtrl', [
        '$scope', 'QuestionNode', 'routeData', 'Authz',
        '$location', 'Notifications', 'Current', 'format',
        'Measure', 'layout',
        function($scope, QuestionNode, routeData, Authz,
                 $location, Notifications, current, format,
                 Measure, layout) {

    $scope.layout = layout;
    $scope.qnode = routeData.parent;
    $scope.program = routeData.program;

    $scope.measure = {
        parent: $scope.qnode,
        responseType: "dummy"
    };

    $scope.select = function(measure) {
        // postData is empty: we don't want to update the contents of the
        // measure; just its links to parents (giving in query string).
        var postData = {};
        Measure.save({
            id: measure.id,
            parentId: $scope.qnode.id,
            programId: $scope.program.id
        }, postData,
            function success(measure, headers) {
                var message = "Saved";
                if (headers('Operation-Details'))
                    message += ': ' + headers('Operation-Details');
                Notifications.set('edit', 'success', message);
                $location.url(format(
                    '/2/qnode/{}?program={}', $scope.qnode.id, $scope.program.id));
            },
            function failure(details) {
                Notifications.set('edit', 'error',
                    "Could not save: " + details.statusText);
            }
        );
    };

    $scope.search = {
        term: "",
        programId: $scope.program.id,
        page: 0,
        pageSize: 10
    };
    $scope.$watch('search', function(search) {
        Measure.query(search).$promise.then(function(measures) {
            $scope.measures = measures;
        });
    }, true);

    $scope.checkRole = Authz({program: $scope.program});
    $scope.QuestionNode = QuestionNode;
    $scope.Measure = Measure;
}])


.directive('errorHeader', function() {
    return {
        restrict: 'A',
        scope: {
            structureNode: '=',
            submissionNode: '='
        },
        templateUrl: '/error_header.html',
        link: function(scope, elem, attrs) {
            elem.addClass('subheader bg-warning');
            scope.$watchGroup(['structureNode.error', 'submissionNode.error'],
                    function(vars) {
                elem.toggleClass('ng-hide', !vars[0] && !vars[1]);
            });
        }
    };
})


;
