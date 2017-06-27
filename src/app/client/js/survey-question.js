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


;
