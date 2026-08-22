module.exports = function(eleventyConfig) {
  eleventyConfig.addPassthroughCopy("src/css");

  eleventyConfig.addFilter("formatMoney", function(value) {
    if (!value) return "";
    return "$" + Math.round(value).toLocaleString("en-AU");
  });

  return {
    dir: {
      input: "src",
      output: "_site",
      includes: "_includes"
    }
  };
};
