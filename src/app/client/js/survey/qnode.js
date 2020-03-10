'use strict';

angular.module('upmark.survey.qnode', [
    'ngResource', 'ngSanitize', 'ui.select', 'ui.sortable',
    'upmark.admin.settings', 'upmark.user', 'upmark.chain'])

/*//#  test use session to keep status
.factory('Status',  ['$resource', function($resource) {
    return $resource('/status', {},
        {  get: { method: 'GET', cache: false }, save: { method: 'POST' },
    });
}])
//###############*/

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
                        submissionId: submission ? submission.id :
                            '',
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
        layout, Arrays, ResponseNode, Response, $timeout, $route) {

    // routeData.parent and routeData.survey will only be defined when
    // creating a new qnode.
    var totalQuestion=0;
    var totalAnswer=0;  
    var responseMeasure=[];  

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
            '/3/qnode/{}?program={}', model.id, $scope.program.id));
    });
    $scope.$on('EditDeleted', function(event, model) {
        if (model.parent) {
            $location.url(format(
                '/3/qnode/{}?program={}', model.parent.id,
                $scope.program.id));
        } else {
            $location.url(format(
                '/3/survey/{}?program={}', model.survey.id,
                $scope.program.id));
        }
    });

    // Used to get history
    $scope.QuestionNode = QuestionNode;

    // get first measure response for all measures response history

    $scope.responseHistory={
        Response: Response
    };

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
     
        $scope.questions={total:0, answer:0};

        $scope.toggleDropdown = function() {             
            if ($scope.showMeasureDetail != null)
                $scope.showMeasureDetail =! $scope.showMeasureDetail
            else
                $scope.showMeasureDetail = true;
            $scope.$broadcast("collapse-expansion", $scope.showMeasureDetail);
        }

        $scope.saveAllResponses = function() {
            $scope.measureNum=0;
            totalQuestion=0;
            totalAnswer=0;
            responseMeasure=[];
            $scope.$broadcast('save-response', { 
                state: $scope.measures[0].response.approval,
                saveAll : true
            });
            /*$scope.rnode = ResponseNode.get({
                submissionId: $scope.submission.id,
                qnodeId: $scope.qnode.id
            });
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
            );*/

        };

        $scope.$on('response-saved-measures', function(events,args) {
            $scope.measureNum=$scope.measureNum+1;
            if ($scope.measureNum==$scope.qnode.nMeasures) {
                //updateInformation
                $scope.rnode = ResponseNode.get({
                     submissionId: $scope.submission.id,
                     qnodeId: $scope.qnode.id
                });

                disableUpdate = true;

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
            }
            if (args==null)
            {
               //totalQuestion=totalQuestion+1;
               //responseMeasure.push('error response');
            
               if (responseMeasure.length==$scope.qnode.nMeasures) {
                   //$scope.totalQuestion=totalQuestion;
                   //$scope.totalAnswer=totalAnswer;  
                }
            }
            
        });

        $scope.$on('response-get-measures', function(events,args) {
            if (!responseMeasure.includes(args.measureId)) {
                if (args.questions)
                  totalQuestion=totalQuestion+args.questions;
                if (args.answerQuestions)
                   totalAnswer=totalAnswer+args.answerQuestions;   
                responseMeasure.push(args.measureId);   
            } 
            if (responseMeasure.length==$scope.qnode.nMeasures) {
                $scope.totalQuestion=totalQuestion;
                $scope.totalAnswer=totalAnswer;  
            }
        });
 
        



        $scope.resetAllResponses = function() {
            $scope.$broadcast('reset-response');
        };



    }


    $scope.$on('get-history-fromQnode', function(event, version) {
        $scope.$broadcast('get-history',  version)  
    });

    $scope.getSubmissionUrl = function(submission) {
        if (submission) {
            return format('/3/qnode/{}?submission={}',
                $scope.qnode.id, submission.id);
        } else {
            return format('/3/qnode/{}?program={}',
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
                    '/3/qnode/{}?program={}', $scope.parent.id, $scope.program.id));
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


.controller('QnodeChildren', ['$scope', '$rootScope', '$http', 'bind', 'Editor', 'QuestionNode', 
        'ResponseNode', 'Notifications',
        function($scope, $rootScope, $http, bind, Editor, QuestionNode, ResponseNode, 
            Notifications) {
/*// test use session to keep status
.controller('QnodeChildren', ['$scope', '$rootScope', '$http','bind', 'Editor', 'QuestionNode', 'Status',
        'ResponseNode', 'Notifications',
        function($scope, $rootScope, $http, bind, Editor, QuestionNode, Status, ResponseNode, 
            Notifications) {
// ###################*/
    //$scope.hideDetail=$rootScope.hideDetail;       

    bind($scope, 'children', $scope, 'model', true);
 
    $scope.checkGroup = function() {
        var hasGroup=false;
        //if (!$scope.submission && $scope.model && $scope.model.length>0) { // group not in survey
        if ($scope.model && $scope.model.length>0) {  // group also in survey
            for (var i=0;i<$scope.model.length;i++) {
                if ($scope.model[i].group) {
                   hasGroup=true;
                  break;  
                } 
            }   
        }   
        return hasGroup;
    }

    $scope.toggleAllDropdown = function() {
        $scope.hideDetail =! $scope.hideDetail;
        $rootScope.hideDetail=$scope.hideDetail;  
        if ($scope.model && $scope.model.length>0) {
            $scope.model.forEach(function(item,index){
               if (item.group) {
                   item.hideDetail =$scope.hideDetail;
               }
            })
        }
    
    }

    $scope.changeOrder = function() {
        if ($scope.checkGroup()) {
            $scope.hideDetail =true;
            $scope.toggleAllDropdown();
        }
        $scope.edit.edit();
   
    }



    $scope.toggleDropdown = function(index) {
        $scope.model[index].hideDetail =! $scope.model[index].hideDetail;
        /*// test use session to keep status
        $scope.status=new Status({ statusList: [{id: $scope.model[index].id, hideDetail: $scope.model[index].hideDetail}] });
        // ##################*/
        for (var i=index+1;i<$scope.model.length;i++) {
            if ($scope.model[index].group==$scope.model[i].group) {
                $scope.model[i].hideDetail =! $scope.model[i].hideDetail;
                /*// test use session to keep status
                $scope.status.statusList.push({id: $scope.model[i].id, hideDetail: $scope.model[i].hideDetail});
                //############ */   
            }
            else
               break;   
        }   
        /*// test use session to keep status
        $scope.status.$save();  */
        /*$http.post('/status',$scope.status).success(function(response){
            Notifications.set('edit', 'success', 'message');
        })
        Status.save({
            
        }, $scope.status,
            function success(measure, headers) {
                var message = "Saved";
                Notifications.set('edit', 'success', message);
            },
            function failure(details) {
                Notifications.set('edit', 'error',
                    "Could not save: " );
            }
        );
        //############    */ 
    };

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
            var hasGroup=false;
            if ($scope.children && $scope.children.length>0) {  // group also in survey
                for (var i=0;i<$scope.children.length;i++) {
                    if ($scope.children[i].group) {
                       hasGroup=true;
                      break;  
                    } 
                }   
            }   
            /*if ($scope.children && $scope.children.length>0) {
                $scope.children.forEach(function(item,index){
                   if (item.group) {
                       item.hideDetail =$scope.hideDetail;
                   }
                })
            }  */
            if (hasGroup) {
                var notQnode = true;
                if ($rootScope.qnodes && $rootScope.qnodes.length>0) {
                    for (var i=0;i<$rootScope.qnodes.length;i++) {
                    //$rootScope.qnodes.forEach(function(item,index){
                        if ($rootScope.qnodes[i].id == $scope.qnode.id) {
                            notQnode = false;
                            var sameStatus=true;
                            if ($scope.children && $scope.children.length>0) {
                                $scope.children.forEach(function(item,index){
                                    if (item.group &&  $rootScope.qnodes[i].children &&  $rootScope.qnodes[i].children.length>0) {
                                        $rootScope.qnodes[i].children.forEach(function(child,index){
                                            if (child.id == item.id)
                                               item.hideDetail = child.hideDetail;
                                        })
                                    }
                                    if (index > 0 && sameStatus) {
                                        sameStatus= ( $scope.children[index-1].hideDetail == $scope.children[index].hideDetail)
                                    }
                                })
                            }
                            if (sameStatus && $scope.children && $scope.children.length>0) {
                                $scope.hideDetail = $scope.children[0].hideDetail;
                            }
                            $rootScope.qnodes[i].children = children;
                            break;
                        }   
                    }        
                }
                if (notQnode) {
                    if ($rootScope.qnodes) {
                        $rootScope.qnodes.push({
                            id: $scope.qnode.id,
                            children: children
                        })
                    }
                    else {

                        $rootScope.qnodes=[ {
                            id: $scope.qnode.id,
                            children: children
                        }]
                    }
                }
            }
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

    $scope.getChildren = function() {
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
    }

    //get update qnode childen list after category level approval change
    $scope.$on("state-changed", function(){
        $scope.getChildren();
    })

    $scope.getChildren();

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
    $scope.$on('saveResponse', function () {
        //args.state would have the state.
        $scope.$broadcast('save-response');
    });

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

    $scope.$on("collapse-expansion", function(event, action){
        $scope.measures.forEach(function(m){
            m.showMeasureDetail=action;
        });
    })

    $scope.toggleDropdown = function(index) {
        var type = 'showMeasureDetail';
        if (this.item['showMeasureDetail'])
           this.item['showMeasureDetail'] = !this.item['showMeasureDetail'];
        else
           this.item['showMeasureDetail'] = true;
        
    };

    $scope.$on('get-history', function(event, version) {
        //set measures history approval
        $scope.model[0].response.approval=version.approval;
    });

}])

.controller('MeasuresCtrl', function(
    $scope, Measure, Editor, Authz,
    $location, Notifications, currentUser, Program, format, layout,
    Structure, Arrays, Response, hotkeys, $q, $timeout, $window,
    responseTypes, ResponseType, Enqueue) {

$scope.layout = layout;
$scope.parent =$scope.item;
$scope.submission = $scope.submission;
$scope.Response = Response;
$scope.model = {
    response: null,
    lastSavedResponse: null,
};

if ($scope.item) {
    // Editing old
    $scope.measure = $scope.item;
} else {
    // Creating new
    $scope.measure = new Measure({
        obType: 'measure',
        parent: $scope.item,
        programId: $scope.item.program.id,
        weight: 100,
        hasSubMeasures: false,
        subMeasures: [],
        responseTypeId: null,
        sourceVars: [],
    });
}

$scope.toggleHasSubMeasures = function(measure) {
    measure.hasSubMeasures = !measure.hasSubMeasures;
    if(measure.hasSubMeasures) {
        if (!measure.subMeasures) measure.subMeasures = [];
        if (measure.subMeasures.length <= 0) $scope.addSubMeasure(measure, $scope.rt);
    }
};
$scope.addSubMeasure = function(measure,rt) {
    if (!measure.subMeasures)  measure.subMeasures = [];
     measure.subMeasures.push({
        description: '',
        responseTypeId: null,
        sourceVars: [],
        rt: rt || {
            definition:  null,
            responseType: null,
            search: {
                programId: $scope.measure.programId,
                pageSize: 5,
            }  
        }     
    });
};

$scope.newResponseType = function(type) {
    var parts;
    if (type == 'multiple_choice') {
        parts = [{type: 'multiple_choice', id: 'a', options: [
            {name: 'No', score: 0},
            //{name: 'Yes', score: 0.5}]
            {name: 'Yes', score: 1}]
        }];
    } else if (type == 'numerical') {
        parts = [{type: 'numerical', id: 'a'}];
    }

    return new ResponseType({
        obType: 'response_type',
        programId: $scope.edit.model.programId,
        name: $scope.edit.model.title,
        parts: parts,
        formula: 'a',
    });
};
$scope.cloneResponseType = function() {
    var rtDef = angular.copy($scope.rt.definition)
    rtDef.id = null;
    rtDef.name = rtDef.name + ' (Copy)'
    rtDef.nMeasures = 0;
    return rtDef;
};
$scope.rt = {
    definition: $scope.item.responseType || null,
    responseType:  null,
    search: {
        programId: $scope.measure.programId,
        pageSize: 5,
    },
};

/*if ($scope.rt.definition) {
    $scope.rt.responseType = new responseTypes.ResponseType(
        $scope.rt.definition.name, $scope.rt.definition.parts, $scope.rt.definition.formula);
};*/


if ($scope.submission) {
    // Get the response that is associated with this measure and submission.
    // Create an empty one if it doesn't exist yet.
    $scope.lastSavedResponse = null;
    $scope.setResponse = function(response) {
        /*//calculate the number of total questions and answer questions
        var totalQuestions=0;
        var answerQuestions=0;

        if ($scope.model.response.subMeasures) {
            totalQuestions=$scope.model.response.subMeasures.length;
            if ($scope.model.response.error==null || $scope.model.response.error=="" )
            {
                answerQuestions=totalQuestions;
            }
        }
        else
        {
            totalQuestions=1;
            if ($scope.model.response.error==null || $scope.model.response.error=="" )
            {
                answerQuestions=1;
            }
        }*/



        if (!response.responseParts)
            response.responseParts = [];
        
        if ($scope.measure.subMeasureList) {
            response.subMeasures=$scope.measure.subMeasureList;

            //calculate the number of total questions and answer questions  
            response.questions=$scope.measure.subMeasureList.length;
            if (response.responseParts.length>0 && (response.error==null || response.error=="" ))
            {
                response.answerQuestions=$scope.measure.subMeasureList.length;
            }
            else {
                response.answerQuestions=0;
            }
        }
        else
        {
            //calculate the number of total questions and answer questions
            response.questions=1;
            if (response.responseParts.length>0 && (response.error==null || response.error=="" ))
            {
                response.answerQuestions=1;
            }
            else {
                response.answerQuestions=0;
            }
        }
        

        $scope.model.response = response;
        $scope.lastSavedResponse = angular.copy(response);
        if ( response.version) {
           $scope.$emit('response-get-measures', response);
        }
    };

    var nullResponse = function(measure, submission) {
        return new Response({
            measureId: $scope.measure ? $scope.measure.id : null,
            submissionId: $scope.submission ? $scope.submission.id : null,
            responseParts: [],
            comment: '',
            notRelevant: false,
            approval: 'draft'
        });
    };
    $scope.setResponse(nullResponse());
    Response.get({
        measureId: $scope.measure.id,
        submissionId: $scope.submission.id
    }).$promise.then(
        function success(response) {
            // should make response_parts change if response_type part type changed
            if (response.responseParts && response.responseParts.length>0 
                && $scope.rt.definition.parts.length==response.responseParts.length) {
                angular.forEach($scope.rt.definition.parts, function(part,index){
                    if ((part.type=='multiple_choice' && response.responseParts[index].value) ||
                        (part.type=='numerical' && response.responseParts[index].index)) {
                        response.responseParts[index]={};
                    }

                });
            }
            else if (response.responseParts && response.responseParts.length>0) {
                // response_type part and response_parts different length 
                response.responseParts=[];
            }
            
            //end type changed
            $scope.setResponse(response);
        },
        function failure(details) {
            if (details.status != 404) {
                Notifications.set('edit', 'error',
                    "Failed to get response details: " + details.statusText);
                return;
            }
            $scope.setResponse(nullResponse(
                $scope.measure, $scope.submission));
        }
    );

    var interceptingLocation = false;
    $scope.$on('$locationChangeStart', function(event, next, current) {
        if (!$scope.model.response.$dirty || interceptingLocation)
            return;
        event.preventDefault();
        interceptingLocation = true;
        $scope.saveResponse().then(
            function success() {
                $window.location.href = next;
                $timeout(function() {
                    interceptingLocation = false;
                });
            },
            function failure(details) {
                var message = "Failed to save: " +
                    details.statusText +
                    ". Are you sure you want to leave this page?";
                var answer = confirm(message);
                if (answer)
                    $window.location.href = next;
                $timeout(function() {
                    interceptingLocation = false;
                });
            }
        );
    });



    $scope.saveResponse = function() {
        return $scope.model.response.$save().then(
            function success(response) {
                $scope.$broadcast('response-saved');
                $scope.$emit('response-saved-measures',response);
                Notifications.set('edit', 'success', "Saved", 5000);
                $scope.setResponse(response);
                return response;
            },
            function failure(details) {
                $scope.$emit('response-saved-measures',null);
                Notifications.set('edit', 'error',
                    "Could not save: " + details.statusText);
                return $q.reject(details);
            });
    };
    $scope.resetResponse = function() {
        $scope.model.response = angular.copy($scope.lastSavedResponse);
    };
    $scope.toggleNotRelvant = function() {
        var oldValue = $scope.model.response.notRelevant;
        $scope.model.response.notRelevant = !oldValue;
        $scope.model.response.$save().then(
            function success(response) {
                Notifications.set('edit', 'success', "Saved", 5000);
                $scope.setResponse(response);
            },
            function failure(details) {
                if (details.status == 403) {
                    Notifications.set('edit', 'info',
                        "Not saved yet: " + details.statusText);
                    if (!$scope.model.response) {
                        $scope.setResponse(nullResponse(
                            $scope.measure, $scope.submission));
                    }
                } else {
                    $scope.model.response.notRelevant = oldValue;
                    Notifications.set('edit', 'error',
                        "Could not save: " + details.statusText);
                }
            });
    };
    $scope.setState = function(state) {
        $scope.model.response.$save({approval: state},
            function success(response) {
                Notifications.set('edit', 'success', "Saved", 5000);
                $scope.setResponse(response);
            },
            function failure(details) {
                Notifications.set('edit', 'error',
                    "Could not save: " + details.statusText);
            }
        );
    };
    $scope.$watch('response', function() {
        $scope.model.response.$dirty = !angular.equals(
            $scope.model.response, $scope.lastSavedResponse);
    }, true);
}

$scope.$on('save-response', function(args) { 
    if (args.targetScope.measures[0].response.approval) {
        $scope.model.response.approval=args.targetScope.measures[0].response.approval;
        $scope.model.response.saveAll=true;
    }
    //$scope.$parent.question.total = $scope.$parent.question.total+$scope.response.questions;
    //$scope.$parent.question.answer = $scope.$parent.question.total+$scope.response.answerQuestion;
    $scope.saveResponse();

});

$scope.$on('reset-response', $scope.resetResponse);

$scope.$watch('measure', function(measure) {
    $scope.structure = Structure(measure, $scope.submission);
    $scope.program = $scope.structure.program;
    $scope.edit = Editor('measure', $scope, {
        parentId: measure.parent && measure.parent.id,
        surveyId: measure.parent && measure.parent.survey.id,
        programId: $scope.program.id
    });
    if (!measure.id)
        $scope.edit.edit();

    if (measure.parents) {
        var parents = [];
        for (var i = 0; i < measure.parents.length; i++) {
            parents.push(Structure(measure.parents[i]));
        }
        $scope.parents = parents;
    }
});
$scope.$watch('structure.program', function(program) {
    $scope.checkRole = Authz({
        program: $scope.program,
        submission: $scope.submission,
    });
    $scope.editable = ($scope.program.isEditable &&
        !$scope.structure.deletedItem &&
        !$scope.submission);
});

var rtDefChanged = Enqueue(function() {
    var rtDef = $scope.rt.definition;
    if (!rtDef) {
        $scope.rt.responseType = null;
        return;
    }
    $scope.rt.responseType = new responseTypes.ResponseType(
        rtDef.name, rtDef.parts, rtDef.formula);
}, 0, $scope);
$scope.$watch('rt.definition', rtDefChanged);
$scope.$watch('rt.definition', rtDefChanged, true);
$scope.$watchGroup(['rt.responseType', 'edit.model'], function(vars) {
    var responseType = vars[0],
        measure = vars[1];
    if (!responseType || !measure || !measure.sourceVars) {
        // A measure only has source variables when viewed in the context
        // of a survey.
        return;
    }
    var measureVariables = measure.sourceVars.filter(
        function(measureVariable) {
            // Remove bindings that have not been set yet
            return measureVariable.sourceMeasure;
        }
    );
    measureVariables.forEach(function(measureVariable) {
        measureVariable.$unused = true;
    });
    responseType.unboundVars.forEach(function(targetField) {
        var measureVariable;
        for (var i = 0; i < measureVariables.length; i++) {
            var mv = measureVariables[i];
            if (mv.targetField == targetField) {
                mv.$unused = false;
                return;
            }
        }
        measureVariables.push({
            targetField: targetField,
            sourceMeasure: null,
            sourceField: null,
        });
    });
    measureVariables.sort(function(a, b) {
        return a.targetField.localeCompare(b);
    });
    measure.sourceVars = measureVariables;
});
$scope.searchMeasuresToBind = function(term) {
    return Measure.query({
        term: term,
        programId: $scope.structure.program.id,
        surveyId: $scope.structure.survey.id,
        withDeclaredVariables: true,
    }).$promise;
};

var applyRtSearch = Enqueue(function() {
    if (!$scope.rt.showSearch)
        return;
    ResponseType.query($scope.rt.search).$promise.then(
        function success(rtDefs) {
            $scope.rt.searchRts = rtDefs;
        },
        function failure(details) {
            Notifications.set('measure', 'error',
                "Could not get response type list: " + details.statusText);
        }
    );
}, 100, $scope);
$scope.$watch('rt.search', applyRtSearch, true);
$scope.$watch('rt.showSearch', applyRtSearch, true);
$scope.chooseResponseType = function(rtDef) {
    ResponseType.get(rtDef, {
        programId: $scope.structure.program.id
    }).$promise.then(function(resolvedRtDef) {
        $scope.rt.definition = resolvedRtDef;
    });
    $scope.rt.showSearch = false;
};

$scope.save = function() {
    if (!$scope.edit.model)
        return;
    if (!$scope.rt.definition) {
        Notifications.set('edit', 'error',
            "Could not save: No repsonse type");
        return;
    }
    $scope.rt.definition.$createOrSave().then(
        function success(definition) {
            var measure = $scope.edit.model;
            if (measure.sourceVars) {
                measure.sourceVars = measure.sourceVars.filter(function(mv) {
                    return !mv.$unused;
                });
            }
            measure.responseTypeId = definition.id;
            return $scope.edit.save();
        },
        function failure(details) {
            Notifications.set('edit', 'error',
                "Could not save: " + details.statusText);
        }
    );
};
$scope.$on('EditSaved', function(event, model) {
    $location.url($scope.getUrl(model));
});
$scope.$on('EditDeleted', function(event, model) {
    if (model.parent) {
        $location.url(format(
            '/3/qnode/{}?program={}', model.parent.id, model.programId));
    } else {
        $location.url(format(
            '/3/measures?program={}', model.programId));
    }
});

$scope.Measure = Measure;

if ($scope.submission) {
    var t_approval;
    if (currentUser.role == 'clerk' || currentUser.role == 'org_admin')
        t_approval = 'final';
    else if (currentUser.role == 'consultant')
        t_approval = 'reviewed';
    else
        t_approval = 'approved';
    hotkeys.bindTo($scope)
        .add({
            combo: ['ctrl+enter'],
            description: "Save the response, and mark it as " + t_approval,
            callback: function(event, hotkey) {
                $scope.setState(t_approval);
            }
        });
}

$scope.getUrl = function(measure) {
    if ($scope.structure.submission) {
        return format('/3/measure/{}?submission={}',
            measure.id, $scope.structure.submission.id);
    } else {
        return format('/3/measure/{}?program={}&survey={}',
            measure.id, $scope.structure.program.id,
            $scope.structure.survey && $scope.structure.survey.id || '');
    }
};

$scope.getSubmissionUrl = function(submission) {
    if (submission) {
        return format('/3/measure/{}?submission={}',
            $scope.measure.id, submission.id,
            $scope.parent && $scope.parent.id || '');
    } else {
        return format('/3/measure/{}?program={}&survey={}',
            $scope.measure.id, $scope.structure.program.id,
            $scope.structure.survey && $scope.structure.survey.id || '');
    }
};
})
