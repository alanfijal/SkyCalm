resource "aws_cloudfront_function" "passenger_pages" {
  name    = "${local.name}-passenger-pages"
  runtime = "cloudfront-js-2.0"
  publish = true
  comment = "Serve the passenger app for client-side page routes"
  code    = <<-JS
    function handler(event) {
      var request = event.request;
      if (["/flights","/demo","/health","/history","/replay","/recordings"].indexOf(request.uri) >= 0) request.uri="/index.html";
      return request;
    }
  JS
}
