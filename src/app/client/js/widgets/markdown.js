'use strict'

angular.module('vpac.widgets.markdown', [])


.filter('markdown', function() {
    var converter = new showdown.Converter({
        strikethrough: true,
        tables: true,
        tasklists: true,
        headerLevelStart: 3,
    });
    return function(text) {
        return converter.makeHtml(text);
    };
})


.directive('markdownEditor', function($sanitize) {
    var converter = new showdown.Converter({
        strikethrough: true,
        tables: true,
        tasklists: true,
        headerLevelStart: 3,
    });
    var toMardownOpts = {
        gfm: true,
        converters: [
            {
                // Start headings at level 3.
                filter: ['h1', 'h2', 'h3', 'h4', 'h5', 'h6'],
                replacement: function(innerHTML, node) {
                    var hLevel = Number(node.tagName.charAt(1)) - 2;
                    if (hLevel < 1)
                        hLevel = 1;
                    var hPrefix = '';
                    for (var i = 0; i < hLevel; i++)
                        hPrefix += '#';
                    return '\n' + hPrefix + ' ' + innerHTML + '\n\n';
                }
            },
        ],
    }
    function postLink(scope, elem, attrs, ngModel) {
        elem.toggleClass('embedded-toolbar', true);

        scope.model = {
            mode: 'rendered',
            viewValue: null
        };

        scope.options = {
            placeholder: {text: ""},
            toolbar: {
                buttons: [
                    {
                        name: 'h1',
                        action: 'append-h3',
                        aria: 'header type 1',
                        tagNames: ['h3'],
                        contentDefault: '<b>H1</b>',
                    },
                    {
                        name: 'h2',
                        action: 'append-h4',
                        aria: 'header type 2',
                        tagNames: ['h4'],
                        contentDefault: '<b>H2</b>',
                    },
                    "bold", "italic", "strikethrough",
                    "subscript", "superscript",
                    "anchor", "image",
                    "header1", "header2", "quote",
                    "orderedlist", "unorderedlist",
                    "removeFormat"
                ],
            },
            imageDragging: false,
            buttonLabels: 'fontawesome',
            disableDoubleReturn: true,
            disableExtraSpaces: true,
        };

        // View to model
        ngModel.$parsers.unshift(function (inputValue) {
            if (scope.model.mode == 'rendered') {
                // Work around messy HTML that gets produced due to use of
                // contenteditable in medium editor.
                // https://github.com/yabwe/medium-editor/issues/543
                var doc = angular.element('<div/>').append(inputValue);
                // Replace direct span children of list items with paragraphs,
                // since that's how they'll be converted from Markdown.
                doc.find('li > span').replaceWith(function() {
                    return '<p>' + this.innerHTML + '</p>';
                });
                // Remove all remaining spans, which are just there to host
                // troublesome inline styles (see bug above).
                doc.find('span').replaceWith(function() {
                    return this.innerHTML;
                });
                // Remove all other style attributes for the same reason.
                doc.find('[style]').attr('style', null);
                // Convert line breaks to double line breaks, which will then
                // be saved as a separate paragraph.
                doc.find('br').replaceWith(function() {
                    return '<br><br>';
                });
                var cleanHtml = doc.html();
                var md = toMarkdown(cleanHtml, toMardownOpts);
                return md;
            } else {
                return inputValue;
            }
        });

        // Model to view
        ngModel.$formatters.unshift(function (inputValue) {
            if (scope.model.mode == 'rendered')
                return $sanitize(converter.makeHtml(inputValue));
            else
                return inputValue;
        });

        ngModel.$render = function render() {
            scope.model.viewValue = ngModel.$viewValue;
        };

        scope.$watch('model.viewValue', function(viewValue) {
            ngModel.$setViewValue(viewValue);
        });

        scope.cycleModes = function() {
            if (scope.model.mode == 'rendered')
                scope.model.mode = 'markdown';
            else
                scope.model.mode = 'rendered';
        };

        scope.$watch('model.mode', function(mode) {
            // Undocumented hack: change the model value to anything else; this
            // value is ignored but it runs the formatters.
            // http://stackoverflow.com/a/28924657/320036
            if (ngModel.$modelValue == 'bar')
                ngModel.$modelValue = 'foo';
            else
                ngModel.$modelValue = 'bar';
        });
    };

    return {
        restrict: 'E',
        scope: {
            placeholder: '@',
            meFocusOn: '=',
            meBlurOn: '=',
        },
        templateUrl: 'markdown_editor.html',
        require: 'ngModel',
        link: postLink,
    };
})
