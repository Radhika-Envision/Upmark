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


.controller('StatisticsCtrl', [
        '$scope', 'QuestionNode', 'routeData', 'Editor', 'Authz',
        '$location', 'Notifications', 'Current', 'format', 'Structure',
        'layout', 'Arrays', 'ResponseNode', 'Statistics', 'Submission',
        '$timeout',
        function($scope, QuestionNode, routeData, Editor, Authz,
                 $location, Notifications, current, format, Structure,
                 layout, Arrays, ResponseNode, Statistics, Submission,
                 $timeout) {

    var boxQuartiles = function(d) {
        var quartiles = [];
        angular.forEach(d.data, function(item, index) {
            quartiles.push([
                item.quartile[0],
                item.quartile[1],
                item.quartile[2]
            ]);
        });
        return quartiles;
    };

    // Inspired by http://informationandvisualization.de/blog/box-plot
    d3.box = function() {
        var width = 1,
            height = 1,
            duration = 0,
            domain = null,
            value = Number,
            // whiskers = boxWhiskers,
            quartiles = boxQuartiles,
            detailChart = detailChart,
            tickFormat = null;

        function wrap(text, width) {
          text.each(function() {
            var text = d3.select(this),
                words = text.text().split(/\s+/).reverse(),
                word,
                line = [],
                lineNumber = 0,
                lineHeight = 1.1, // ems
                y = text.attr("y"),
                dy = parseFloat(text.attr("dy")),
                tspan = text.text(null).append("tspan")
                    .attr("x", 0).attr("y", y).attr("dy", dy + "em");
            while (word = words.pop()) {
              line.push(word);
              tspan.text(line.join(" "));
              if (tspan.node().getComputedTextLength() > width) {
                line.pop();
                tspan.text(line.join(" "));
                line = [word];
                tspan = text.append("tspan")
                    .attr("x", 0).attr("y", y)
                    .attr("dy", ++lineNumber * lineHeight + dy + "em")
                    .text(word);
              }
            }
          });
        }

        function type(d) {
          d.value = +d.value;
          return d;
        }

      // For each small multiple…
        function box(g) {
            g.each(function(d, i) {
                var g = d3.select(this),
                    n = d.length;

                var checkOverlapping =
                    function(tickValues, itemValue, itemIndex, yAxis) {
                        var gap = 0;
                        angular.forEach(tickValues, function(tick, index) {
                            if (index != itemIndex &&
                                Math.abs(yAxis(itemValue)-yAxis(tick)) < 7)
                                gap = 10;
                        });
                        return gap;
                };

                var displayChart = function (object, dataIndex, compareMode) {
                    var lineWidth = !object.compareMode ? width : width / 2 - 1;
                    var data = object.data[dataIndex];
                    // Compute the new x-scale.
                    var yAxis = d3.scale.linear()
                      .domain([data.min, data.max])
                      .range([height - 40, 20]);

                     // Compute the tick format.
                    var format = tickFormat || yAxis.tickFormat(8);
                    var line20 = (data.max - data.min) * 0.2;
                    var borderData = [data.min,
                                      data.min + line20,
                                      data.min + line20 * 2,
                                      data.min + line20 * 3,
                                      data.min + line20 * 4,
                                      data.max];
                    var borderClass = ["border",
                                       "border20",
                                       "border20",
                                       "border20",
                                       "border20",
                                       "border"]

                    if (dataIndex==0) {
                        var border = g.selectAll("line.border")
                            .data(borderData);

                        border.enter().insert("line")
                            .attr("class", function(item, i) {
                                return borderClass[i];
                            })
                            .attr("x1", -50)
                            .attr("y1", yAxis)
                            .attr("x2", 70)
                            .attr("y2", yAxis);
                    }

                    g.append("line", "rect")
                        .attr("class", "center")
                        .attr("x1", width / 2)
                        .attr("y1", yAxis(data.survey_min))
                        .attr("x2", width / 2)
                        .attr("y2", yAxis(data.survey_max));

                    // Update innerquartile box.
                    g.append("rect")
                        .attr("class", "box")
                        .attr("x", (dataIndex==0 ? 0: width/2) + 0.5)
                        .attr("y", Math.round(yAxis(data.quartile[2])) + 0.5)
                        .attr("width", lineWidth)
                        .attr("height", Math.round(yAxis(data.quartile[0])
                                - yAxis(data.quartile[2])) - 1);

                    // Update whisker ticks. These are handled separately from the box
                    // ticks because they may or may not exist, and we want don't want
                    // to join box ticks pre-transition with whisker ticks post-.
                    var tickData = [data.min,                   // 0
                                    data.survey_min,            // 1
                                    data.quartile[1],           // 2
                                    data.current,               // 3
                                    data.survey_max,            // 4
                                    data.max];                  // 5

                    var tickClass = ["whisker_text",
                                     "whisker_text",
                                     "median_text",
                                     "current_text",
                                     "whisker_text",
                                     "whisker_text"];

                    // text tick
                    g.selectAll("text.whisker" + dataIndex)
                        .data(tickData)
                        .enter().append("text")
                        .attr("class", function(item, index) {
                            return "tick " + tickClass[index];
                        })
                        .attr("dy", ".3em")
                        .attr("dx", dataIndex==0 ? -30:5)
                        .attr("x", width)
                        .attr("y", function(item, index) {
                            // top and bottom value display
                            if (index==0)
                                return yAxis(item)+13;
                            if (index==5)
                                return yAxis(item)-10;
                            var gap = 0;
                            if (index != 3)
                                gap = checkOverlapping(tickData, item, index,
                                    yAxis);

                            return yAxis(item) + gap;

                        })
                        .attr("text-anchor", dataIndex==0 ? "end":"start")
                        .text(format);

                    var lineData = [data.survey_min,            // 0
                                    data.survey_max,            // 1
                                    data.quartile[1],           // 2
                                    data.current];              // 3

                    var lineClass = ["whisker",
                                     "whisker",
                                     "median",
                                     "current"];

                    g.selectAll("line.whisker" + dataIndex)
                        .data(lineData)
                        .enter().append("line")
                        .attr("class", function(item, index) {
                            return lineClass[index];
                        })
                        .attr("x1", function(item, index) {
                            if(index == 3)
                                return dataIndex==0 ? -4:width/2;
                            return dataIndex==0 ? 0:width/2;
                        })
                        .attr("y1", function(item, index) {
                            return Math.round(yAxis(item));
                        })
                        .attr("x2", function(item, index) {
                            if(compareMode) {
                                if(index == 3)
                                    return dataIndex==0 ? width/2:width+5;
                                return dataIndex==0 ? width/2:width;
                            } else {
                                if(index == 3)
                                    return width+5;
                                return width + 1;
                            }
                        })
                        .attr("y2", function(item, index) {
                            return Math.round(yAxis(item));
                        });

                    if (dataIndex == 0) {
                        g.append("text")
                            .attr("class", "title")
                            .attr("x", 0)
                            .attr("y", yAxis(0) - 20)
                            .attr("dy", 5)
                            .attr("text-anchor", "middle")
                            .text(d.title)
                            .call(wrap, 100);
                    }
                };

                displayChart(d, 0, d.compareMode);

                if (d.compareMode) {
                    displayChart(d, 1, d.compareMode);
                }
            });
            d3.timer.flush();
        }

        box.width = function(x) {
            if (!arguments.length) return width;
                width = x;
            return box;
        };

        box.height = function(x) {
            if (!arguments.length) return height;
                height = x;
            return box;
        };

        box.tickFormat = function(x) {
            if (!arguments.length) return tickFormat;
                tickFormat = x;
            return box;
        };

        box.duration = function(x) {
            if (!arguments.length) return duration;
                duration = x;
            return box;
        };

        box.domain = function(x) {
            if (!arguments.length) return domain;
                domain = x == null ? x : d3.functor(x);
            return box;
        };

        box.value = function(x) {
            if (!arguments.length) return value;
                value = x;
            return box;
        };

        box.whiskers = function() {
            return box;
        };

        box.quartiles = function(x) {
            if (!arguments.length) return quartiles;
                quartiles = x;
            return box;
        };

        box.detailChart = function(x) {
            if (!arguments.length) return detailChart;
                detailChart = x;
            return box;
        };

        return box;
    };

    // Start custom logic here
    $scope.submission1 = routeData.submission1;
    $scope.submission2 = routeData.submission2;
    $scope.rnodes1 = routeData.rnodes1;
    $scope.rnodes2 = routeData.rnodes2;
    $scope.stats1 = routeData.stats1;
    $scope.stats2 = routeData.stats2;
    $scope.qnode1 = routeData.qnode1;
    $scope.qnode2 = routeData.qnode2;
    $scope.approval = routeData.approval;
    $scope.allowedStates = routeData.approvals;
    $scope.struct1 = Structure(
        routeData.qnode1 || routeData.submission1.survey,
        routeData.submission1);
    if (routeData.submission2) {
        $scope.struct2 = Structure(
            routeData.qnode2 || routeData.submission2.survey,
            routeData.submission2);
    }
    $scope.layout = layout;

    $scope.getSubmissionUrl1 = function(submission) {
        var query;
        if (submission) {
            query = format('submission1={}&submission2={}',
                submission.id,
                $scope.submission2 ? $scope.submission2.id : '');
        } else {
            query = format('submission1={}',
                $scope.submission2 ? $scope.submission2.id : '');
        }
        return format('/2/statistics?{}&qnode={}&approval={}',
            query, $location.search()['qnode'] || '', $scope.approval);
    };
    $scope.getSubmissionUrl2 = function(submission) {
        var query;
        if (submission) {
            query = format('submission1={}&submission2={}',
                $scope.submission1 ? $scope.submission1.id : '',
                submission.id);
        } else {
            query = format('submission1={}',
                $scope.submission1 ? $scope.submission1.id : '');
        }
        return format('/2/statistics?{}&qnode={}&approval={}',
            query, $location.search()['qnode'] || '', $scope.approval);
    };

    $scope.getNavUrl = function(item, key) {
        var aid1 = $scope.submission1.id;
        var aid2 = $scope.submission2 ? $scope.submission2.id : ''
        if (item.path == 'qnode') {
            return format(
                '#/2/statistics?submission1={}&submission2={}&qnode={}&approval={}',
                aid1, aid2, key, $scope.approval);
        } else if (item.path == 'submission') {
            return format(
                '#/2/statistics?submission1={}&submission2={}&approval={}',
                aid1, aid2, $scope.approval);
        }
        return null;
    };

    $scope.chooser = false;
    $scope.toggleDropdown = function(num) {
        if ($scope.chooser == num)
            $scope.chooser = null;
        else
            $scope.chooser = num;
    };

    $scope.$watch('approval', function(approval) {
        $location.search('approval', approval);
    });

    var margin = {top: 10, right: 50, bottom: 20, left: 50},
        width = 120 - margin.left - margin.right,
        height = 600 - margin.top - margin.bottom;

    var chart = d3.box()
        .whiskers()
        .width(width)
        .height(height);

    var svg = d3.select("#chart").selectAll("svg");

    var data = [];

    var drawChart = function() {
        if (data.length > 0) {
            svg.data(data)
                .enter().append("svg")
                    .attr("class", "box")
                    .attr("width", width + margin.left + margin.right)
                    .attr("height", height + margin.bottom + margin.top)
                    .on("click", function(d) {
                        $location.search('qnode', d.id);
                    })
                .append("g")
                    .attr("transform",
                          "translate(" + margin.left + "," + margin.top + ")")
                    .call(chart);
        } else {
            var svgContainer = svg.data(["No Data"]).enter().append("svg")
                .attr("width", 1000)
                .attr("height", height);
            svgContainer.append("text")
                .attr("x", 500)
                .attr("y", height / 4)
                .attr("text-anchor", "middle")
                .attr("class", "info")
                .text("No Data");
        }

    };

    var fillData = function(submission, rnodes, stats) {
        if (rnodes.length == 0)
            return;

        if (data.length == 0) {
            for (var i = 0; i < rnodes.length; i++) {
                var node = rnodes[i];
                var stat = stats.filter(function(s) {
                    if(s.qnodeId == node.qnode.id) {
                        return s;
                    }
                });
                if (stat.length) {
                    stat = stat[0];
                    var item = {'id': node.qnode.id, 'compareMode': false,
                             'data': [], 'title' : stat.title };
                    item['data'].push({
                                        'current': node.score,
                                        'max': node.qnode.totalWeight,
                                        'min': 0,
                                        'survey_max': stat.max,
                                        'survey_min': stat.min,
                                        'quartile': stat.quartile});
                    data.push(item);
                }
            };

        } else {
            for (var i = 0; i < data.length; i++) {
                var item = data[i];
                item["compareMode"] = true;
                var stat = stats.filter(function(s) {
                    if(s.qnodeId == item.id) {
                        return s;
                    }
                });
                var node = rnodes.filter(function(n) {
                    if(n.qnode.id == item.id) {
                        return n;
                    }
                });

                if (stat.length && node.length) {
                    stat = stat[0];
                    node = node[0];
                    item['data'].push({
                                        'current': node.score,
                                        'max': node.qnode.totalWeight,
                                        'min': 0,
                                        'survey_max': stat.max,
                                        'survey_min': stat.min,
                                        'quartile': stat.quartile});

                } else {
                    item['data'].push({
                                        'current': 0,
                                        'max': 0,
                                        'min': 0,
                                        'survey_max': 0,
                                        'survey_min': 0,
                                        'quartile': [0, 0, 0]});
                }
            };
        }
    };

    fillData($scope.submission1, $scope.rnodes1, $scope.stats1);
    if ($scope.submission2)
        fillData($scope.submission2, $scope.rnodes2, $scope.stats2);

    drawChart();
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
