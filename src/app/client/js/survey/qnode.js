'use strict';

angular.module('upmark.survey.qnode', [
    'ngResource', 'ngSanitize', 'ui.select', 'ui.sortable',
    'upmark.admin.settings', 'upmark.user', 'upmark.chain'])


.config(function($routeProvider, chainProvider) {
    $routeProvider
        .when('/:uv/qnode/new', {
            templateUrl : 'qnode.html',
            controller : 'QuestionNodeCtrl',
            resolve: {routeData: chainProvider({
                survey: ['Survey', '$route',
                        function(Survey, $route) {
                    var surveyId = $route.current.params.survey;
                    if (!surveyId)
                        return null
                    return Survey.get({
                        id: surveyId,
                        programId: $route.current.params.program
                    }).$promise;
                }],
                parent: ['QuestionNode', '$route',
                        function(QuestionNode, $route) {
                    var parentId = $route.current.params.parent;
                    if (!parentId)
                        return null;
                    return QuestionNode.get({
                        id: parentId,
                        programId: $route.current.params.program
                    }).$promise;
                }]
            })}
        })
        .when('/:uv/qnode/:qnode', {
            templateUrl : 'qnode.html',
            controller : 'QuestionNodeCtrl',
            resolve: {routeData: chainProvider({
                submission: ['Submission', '$route',
                        function(Submission, $route) {
                    if (!$route.current.params.submission)
                        return null;
                    return Submission.get({
                        id: $route.current.params.submission
                    }).$promise;
                }],
                qnode: ['QuestionNode', '$route', 'submission',
                        function(QuestionNode, $route, submission) {
                    return QuestionNode.get({
                        id: $route.current.params.qnode,
                        programId: submission ? submission.program.id :
                            $route.current.params.program,
                    }).$promise;
                }],
                measures: ['Measure', '$route', 'submission',
                        function(Measure, $route, submission) {
                    return Measure.query({
                        qnodeId: $route.current.params.qnode,
                        programId: submission ? submission.program.id :
                            $route.current.params.program,
                    }).$promise;
                }]
            })}
        })
        .when('/:uv/qnode-link', {
            templateUrl : 'qnode_link.html',
            controller : 'QnodeLinkCtrl',
            resolve: {routeData: chainProvider({
                survey: ['Survey', '$route',
                        function(Survey, $route) {
                    if (!$route.current.params.survey)
                        return null;
                    return Survey.get({
                        id: $route.current.params.survey,
                        programId: $route.current.params.program
                    }).$promise;
                }],
                parent: ['QuestionNode', '$route',
                        function(QuestionNode, $route) {
                    if (!$route.current.params.parent)
                        return null;
                    return QuestionNode.get({
                        id: $route.current.params.parent,
                        programId: $route.current.params.program
                    }).$promise;
                }],
                program: ['Program', '$route', function(Program, $route) {
                    return Program.get({
                        id: $route.current.params.program
                    }).$promise;
                }],
            })}
        })
    ;
})


.factory('QuestionNode', ['$resource', 'paged', function($resource, paged) {
    return $resource('/qnode/:id.json', {id: '@id'}, {
        get: { method: 'GET', cache: false },
        create: { method: 'POST' },
        save: { method: 'PUT' },
        query: {
            method: 'GET', isArray: true, cache: false,
            interceptor: {response: paged}
        },
        reorder: { method: 'PUT', isArray: true },
        history: { method: 'GET', url: '/qnode/:id/program.json',
            isArray: true, cache: false }
    });
}])


.controller('QuestionNodeCtrl', function(
        $scope, QuestionNode, routeData, Editor, Authz,
        $location, Notifications, format, Structure,
        layout, Arrays, ResponseNode, $timeout, $route) {

    // routeData.parent and routeData.survey will only be defined when
    // creating a new qnode.

    $scope.layout = layout;
    $scope.submission = routeData.submission;
    if (routeData.qnode) {
        // Editing old
        $scope.qnode = routeData.qnode;
        $scope.children = routeData.children;
        $scope.measures = routeData.measures;
    } else {
        // Creating new
        $scope.qnode = new QuestionNode({
            obType: 'qnode',
            parent: routeData.parent,
            survey: routeData.survey
        });
        $scope.children = null;
        $scope.measures = null;
    }

    $scope.$watchGroup(['qnode', 'qnode.deleted'], function() {
        $scope.structure = Structure($scope.qnode, $scope.submission);
        $scope.program = $scope.structure.program;
        $scope.edit = Editor('qnode', $scope, {
            parentId: routeData.parent && routeData.parent.id,
            surveyId: routeData.survey && routeData.survey.id,
            programId: $scope.program.id
        });
        if (!$scope.qnode.id)
            $scope.edit.edit();

        var levels = $scope.structure.survey.structure.levels;
        $scope.currentLevel = levels[$scope.structure.qnodes.length - 1];
        $scope.nextLevel = levels[$scope.structure.qnodes.length];

        $scope.checkRole = Authz({
            program: $scope.program,
            survey: $scope.structure.survey,
            submission: $scope.submission,
        });
        $scope.editable = ($scope.program.isEditable &&
            !$scope.structure.deletedItem &&
            !$scope.submission);
    });

    $scope.$on('EditSaved', function(event, model) {
        $location.url(format(
            '/2/qnode/{}?program={}', model.id, $scope.program.id));
    });
    $scope.$on('EditDeleted', function(event, model) {
        if (model.parent) {
            $location.url(format(
                '/2/qnode/{}?program={}', model.parent.id,
                $scope.program.id));
        } else {
            $location.url(format(
                '/2/survey/{}?program={}', model.survey.id,
                $scope.program.id));
        }
    });

    // Used to get history
    $scope.QuestionNode = QuestionNode;

    if ($scope.submission) {
        $scope.rnode = ResponseNode.get({
            submissionId: $scope.submission.id,
            qnodeId: $scope.qnode.id
        });

        var disableUpdate = false;
        var importanceToView = function() {
            // When saving, the server may choose to change these values.
            // Temporarily disable updates to prevent a save-loop.
            var rnode = $scope.rnode;
            $scope.stats.importance = rnode.importance || rnode.maxImportance;
            $scope.stats.urgency = rnode.urgency || rnode.maxUrgency;

            disableUpdate = true;
            $timeout(function() {
                disableUpdate = false;
            });
        };

        $scope.updateStats = function(rnode) {
            $scope.stats = {
                score: rnode.score,
                progressItems: [
                    {
                        name: 'Draft',
                        value: rnode.nDraft,
                        fraction: rnode.nDraft / $scope.qnode.nMeasures
                    },
                    {
                        name: 'Final',
                        value: rnode.nFinal,
                        fraction: rnode.nFinal / $scope.qnode.nMeasures
                    },
                    {
                        name: 'Reviewed',
                        value: rnode.nReviewed,
                        fraction: rnode.nReviewed / $scope.qnode.nMeasures
                    },
                    {
                        name: 'Approved',
                        value: rnode.nApproved,
                        fraction: rnode.nApproved / $scope.qnode.nMeasures
                    },
                ],
                approval: rnode.nApproved >= $scope.qnode.nMeasures ?
                        'approved' :
                    rnode.nReviewed >= $scope.qnode.nMeasures ?
                        'reviewed' :
                    rnode.nFinal >= $scope.qnode.nMeasures ?
                        'final' :
                        'draft',
                relevance: rnode.nNotRelevant >= $scope.qnode.nMeasures ?
                        'RELEVANT' : 'NOT_RELEVANT',
                promote: 'BOTH',
                missing: 'CREATE',
            };
            importanceToView();
        };

        $scope.rnode.$promise.then(
            function success(rnode) {
                $scope.rnodeDup = angular.copy(rnode);
                $scope.updateStats(rnode);
            },
            function failure(details) {
                Notifications.set('edit', 'error',
                    "Failed to get response details: " + details.statusText);
                return;
            }
        );

        $scope.saveRnode = function() {
            $scope.rnode.$save().then(
                function success(rnode) {
                    $scope.rnodeDup = angular.copy(rnode);
                    $scope.updateStats(rnode);
                    Notifications.set('edit', 'success', "Saved", 5000);
                },
                function failure(details) {
                    angular.copy($scope.rnodeDup, $scope.rnode)
                    Notifications.set('edit', 'error',
                        "Could not save: " + details.statusText);
                });
        };
        $scope.$watch('stats.importance', function(v, vOld) {
            if (disableUpdate || vOld === undefined)
                return;
            $scope.rnode.importance = v;
        });
        $scope.$watch('stats.urgency', function(v, vOld) {
            if (disableUpdate || vOld === undefined)
                return;
            $scope.rnode.urgency = v;
        });
        $scope.$watchGroup(
                ['rnode.notRelevant', 'rnode.importance', 'rnode.urgency'],
                function(vals, oldVals) {
            if (oldVals.every(function(v) { return v === undefined }))
                return;
            if (disableUpdate)
                return;
            $scope.saveRnode();
        });

        $scope.showBulkApproval = false;
        $scope.toggleBulk = function() {
            $scope.showBulkApproval = !$scope.showBulkApproval;
        };
        $scope.showBulkNa = false;
        $scope.toggleBulkNa = function() {
            $scope.showBulkNa = !$scope.showBulkNa;
        };

        $scope.promotionOptions = [{
            name: 'BOTH',
            desc: "Promote and demote existing responses to match chosen state",
        }, {
            name: 'PROMOTE',
            desc: "Only promote existing responses",
        }, {
            name: 'DEMOTE',
            desc: "Only demote existing responses",
        },];

        $scope.missingOptions = [{
            name: 'CREATE',
            desc: "Create responses where they are missing and mark as Not Relevant",
        }, {
            name: 'IGNORE',
            desc: "Don't create missing responses",
        },];

        $scope.relevanceOptions = [{
            name: 'NOT_RELEVANT',
            desc: "Mark all responses as Not Relevant",
        }, {
            name: 'RELEVANT',
            desc: "Mark all responses as Relevant",
        },];

        var bulkAction = function(params) {
            $scope.rnode.$save(params,
                function success(rnode, getResponseHeaders) {
                    var message = "Saved";
                    if (getResponseHeaders('Operation-Details'))
                        message += ": " + getResponseHeaders('Operation-Details');
                    Notifications.set('edit', 'success', message, 5000);
                    // Need to actually reload the route because the list of
                    // children and measures will have changed too.
                    $route.reload();
                },
                function failure(details) {
                    angular.copy($scope.rnodeDup, $scope.rnode)
                    Notifications.set('edit', 'error',
                        "Could not save: " + details.statusText);
                }
            );
        };
        $scope.setState = function(approval, $event) {
            var promote;
            if ($scope.stats.promote == 'BOTH')
                promote = ['PROMOTE', 'DEMOTE'];
            else if ($scope.stats.promote == 'PROMOTE')
                promote = ['PROMOTE'];
            else
                promote = ['DEMOTE'];

            bulkAction({
                approval: approval,
                promote: promote,
                missing: $scope.stats.missing,
            });
            // Stop the approval being set on the rnode; that will happen
            // asynchronously.
            $event.preventDefault();
        };
        $scope.setNotRelevant = function(relevance) {
            bulkAction({
                relevance: relevance,
                missing: $scope.stats.missing,
            });
        };

        $scope.demoStats = [
            {
                name: 'Draft',
                value: 120,
                fraction: 12/12
            },
            {
                name: 'Final',
                value: 100,
                fraction: 10/12
            },
            {
                name: 'Reviewed',
                value: 80,
                fraction: 8/12
            },
            {
                name: 'Approved',
                value: 60,
                fraction: 6/12
            },
        ];
    }

    $scope.getSubmissionUrl = function(submission) {
        if (submission) {
            return format('/2/qnode/{}?submission={}',
                $scope.qnode.id, submission.id);
        } else {
            return format('/2/qnode/{}?program={}',
                $scope.qnode.id, $scope.program.id);
        }
    };
})


.controller('QnodeLinkCtrl', function(
        $scope, QuestionNode, routeData, Authz,
        $location, Notifications, format,
        layout, Structure) {

    $scope.layout = layout;
    $scope.survey = routeData.survey;
    $scope.parent = routeData.parent;
    $scope.program = routeData.program;

    $scope.qnode = {
        obType: 'qnode',
        survey: $scope.parent ? $scope.parent.survey : $scope.survey,
        parent: $scope.parent
    };
    $scope.structure = Structure($scope.qnode);

    $scope.select = function(qnode) {
        // postData is empty: we don't want to update the contents of the
        // qnode; just its links to parents (giving in query string).
        var postData = {};
        QuestionNode.save({
            id: qnode.id,
            parentId: $scope.parent.id,
            programId: $scope.program.id
        }, postData,
            function success(measure, headers) {
                var message = "Saved";
                if (headers('Operation-Details'))
                    message += ': ' + headers('Operation-Details');
                Notifications.set('edit', 'success', message);
                $location.url(format(
                    '/2/qnode/{}?program={}', $scope.parent.id, $scope.program.id));
            },
            function failure(details) {
                Notifications.set('edit', 'error',
                    "Could not save: " + details.statusText);
            }
        );
    };

    $scope.search = {
        level: $scope.structure.qnodes.length - 1,
        parent__not: $scope.parent ? $scope.parent.id : '',
        term: "",
        deleted: false,
        programId: $scope.program.id,
        surveyId: $scope.structure.survey.id,
        desc: true,
        page: 0,
        pageSize: 10
    };
    $scope.$watch('search', function(search) {
        QuestionNode.query(search).$promise.then(function(qnodes) {
            $scope.qnodes = qnodes;
        });
    }, true);

    $scope.checkRole = Authz({
        program: $scope.program,
        survey: $scope.structure.survey,
    });
    $scope.QuestionNode = QuestionNode;
})


.controller('QnodeChildren', ['$scope', 'bind', 'Editor', 'QuestionNode',
        'ResponseNode', 'Notifications',
        function($scope, bind, Editor, QuestionNode, ResponseNode,
            Notifications) {

    bind($scope, 'children', $scope, 'model', true);

    $scope.edit = Editor('model', $scope, {}, QuestionNode);
    $scope.$on('EditSaved', function(event, model) {
        event.stopPropagation();
    });

    $scope.dragOpts = {
        axis: 'y',
        handle: '.grab-handle'
    };

    if ($scope.submission) {
        $scope.query = 'submission=' + $scope.submission.id;
    } else if ($scope.survey) {
        $scope.query = 'program=' + $scope.program.id;
        $scope.query += '&survey=' + $scope.survey.id;
        $scope.edit.params = {
            programId: $scope.program.id,
            surveyId: $scope.survey.id,
            root: ''
        }
    } else {
        $scope.query = 'program=' + $scope.program.id;
        $scope.edit.params.parentId = $scope.qnode.id;
        $scope.edit.params = {
            programId: $scope.program.id,
            parentId: $scope.qnode.id
        }
    }

    $scope.search = {
        deleted: false
    };
    $scope.$watchGroup(['search.deleted', 'survey.id',
                        'submission.survey.id', 'qnode.id'], function(vars) {
        var deleted = vars[0];
        var hid = vars[1] || vars[2];
        var qid = vars[3];
        if (!hid && !qid)
            return;

        QuestionNode.query({
            parentId: qid,
            surveyId: hid,
            programId: $scope.program.id,
            root: qid ? undefined : '',
            deleted: deleted
        }, function(children) {
            $scope.children = children;
        });
    });

    $scope.$watchGroup(['survey', 'structure'], function(vars) {
        var level;
        if ($scope.submission && !$scope.qnode)
            level = $scope.submission.survey.structure.levels[0];
        else if ($scope.survey)
            level = $scope.survey.structure.levels[0];
        else
            level = $scope.nextLevel;
        $scope.level = level;
    });

    if ($scope.submission) {
        // Get the responses that are associated with this qnode and submission.
        ResponseNode.query({
            submissionId: $scope.submission.id,
            parentId: $scope.qnode ? $scope.qnode.id : null,
            surveyId: $scope.survey ? $scope.survey.id : null,
            root: $scope.qnode ? null : ''
        }).$promise.then(
            function success(rnodes) {
                var rmap = {};
                for (var i = 0; i < rnodes.length; i++) {
                    var rnode = rnodes[i];
                    var nm = rnode.qnode.nMeasures;
                    rmap[rnode.qnode.id] = {
                        score: rnode.score,
                        notRelevant: rnode.nNotRelevant >= nm,
                        progressItems: [
                            {
                                name: 'Draft',
                                value: rnode.nDraft,
                                fraction: rnode.nDraft / nm
                            },
                            {
                                name: 'Final',
                                value: rnode.nFinal,
                                fraction: rnode.nFinal / nm
                            },
                            {
                                name: 'Reviewed',
                                value: rnode.nReviewed,
                                fraction: rnode.nReviewed / nm
                            },
                            {
                                name: 'Approved',
                                value: rnode.nApproved,
                                fraction: rnode.nApproved / nm
                            },
                        ],
                        importance: rnode.maxImportance,
                        urgency: rnode.maxUrgency,
                        error: rnode.error,
                    };
                }
                $scope.rnodeMap = rmap;
            },
            function failure(details) {
                Notifications.set('edit', 'error',
                    "Could not get aggregate scores: " +
                    details.statusText);
            }
        );
    }
    var dummyStats = {
        score: 0,
        notRelevant: false,
        progressItems: [
            {
                name: 'Draft',
                value: 0,
                fraction: 0
            },
            {
                name: 'Final',
                value: 0,
                fraction: 0
            },
            {
                name: 'Reviewed',
                value: 0,
                fraction: 0
            },
            {
                name: 'Approved',
                value: 0,
                fraction: 0
            },
        ],
        importance: 0,
        urgency: 0,
        error: null,
    };
    $scope.getStats = function(qnodeId) {
        if ($scope.rnodeMap && $scope.rnodeMap[qnodeId])
            return $scope.rnodeMap[qnodeId];
        else
            return dummyStats;
    };
}])


.controller('QnodeMeasures', ['$scope', 'bind', 'Editor', 'Measure', 'Response',
        'Notifications',
        function($scope, bind, Editor, Measure, Response, Notifications) {

    bind($scope, 'measures', $scope, 'model', true);

    $scope.edit = Editor('model', $scope, {}, Measure);
    $scope.$on('EditSaved', function(event, model) {
        event.stopPropagation();
    });

    $scope.dragOpts = {
        axis: 'y',
        handle: '.grab-handle'
    };

    if ($scope.submission) {
        $scope.query = 'submission=' + $scope.submission.id;
    } else {
        $scope.query = 'program=' + $scope.program.id;
        $scope.query += "&survey=" + $scope.qnode.survey.id;
    }

    $scope.edit.params = {
        programId: $scope.program.id,
        qnodeId: $scope.qnode.id
    }

    $scope.level = $scope.structure.survey.structure.measure;

    if ($scope.submission) {
        // Get the responses that are associated with this qnode and submission.
        Response.query({
            submissionId: $scope.submission.id,
            qnodeId: $scope.qnode.id
        }).$promise.then(
            function success(responses) {
                var rmap = {};
                for (var i = 0; i < responses.length; i++) {
                    var r = responses[i];
                    var nApproved = r.approval == 'approved' ? 1 : 0;
                    var nReviewed = r.approval == 'reviewed' ? 1 : nApproved;
                    var nFinal = r.approval == 'final' ? 1 : nReviewed;
                    var nDraft = r.approval == 'draft' ? 1 : nFinal;
                    rmap[r.measure.id] = {
                        score: r.score,
                        notRelevant: r.notRelevant,
                        progressItems: [
                            {
                                name: 'Draft',
                                value: nDraft,
                                fraction: nDraft
                            },
                            {
                                name: 'Final',
                                value: nFinal,
                                fraction: nFinal
                            },
                            {
                                name: 'Reviewed',
                                value: nReviewed,
                                fraction: nReviewed
                            },
                            {
                                name: 'Approved',
                                value: nApproved,
                                fraction: nApproved
                            },
                        ],
                        error: r.error
                    };
                }
                $scope.responseMap = rmap;
            },
            function failure(details) {
                Notifications.set('edit', 'error',
                    "Could not get aggregate scores: " +
                    details.statusText);
            }
        );
    }
    var dummyStats = {
        score: 0,
        notRelevant: false,
        progressItems: [
            {
                name: 'Draft',
                value: 0,
                fraction: 0
            },
            {
                name: 'Final',
                value: 0,
                fraction: 0
            },
            {
                name: 'Reviewed',
                value: 0,
                fraction: 0
            },
            {
                name: 'Approved',
                value: 0,
                fraction: 0
            },
        ],
        error: null
    };
    $scope.getStats = function(measureId) {
        if ($scope.responseMap && $scope.responseMap[measureId])
            return $scope.responseMap[measureId];
        else
            return dummyStats;
    };
}])
