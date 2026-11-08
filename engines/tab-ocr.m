#import <Foundation/Foundation.h>
#import <Vision/Vision.h>
int main(int argc, const char *argv[]) { @autoreleasepool {
 if(argc<2) return 1;
 VNRecognizeTextRequest *request=[[VNRecognizeTextRequest alloc] init];
 request.recognitionLevel=VNRequestTextRecognitionLevelAccurate;
 request.usesLanguageCorrection=NO;
 request.recognitionLanguages=@[@"en-US"];
 VNImageRequestHandler *handler=[[VNImageRequestHandler alloc] initWithURL:[NSURL fileURLWithPath:@(argv[1])] options:@{}];
 NSError *error=nil;
 if(![handler performRequests:@[request] error:&error]) { fprintf(stderr,"%s",error.description.UTF8String); return 1; }
 NSMutableArray *items=[NSMutableArray array];
 NSRegularExpression *regex=[NSRegularExpression regularExpressionWithPattern:@"[0-9]+" options:0 error:nil];
 for(VNRecognizedTextObservation *obs in request.results) {
  VNRecognizedText *text=[[obs topCandidates:1] firstObject];
  for(NSTextCheckingResult *match in [regex matchesInString:text.string options:0 range:NSMakeRange(0,text.string.length)]) {
   VNRectangleObservation *box=[text boundingBoxForRange:match.range error:nil];
   if(box) [items addObject:@{@"text":[text.string substringWithRange:match.range],@"x":@(CGRectGetMidX(box.boundingBox)),@"y":@(1-CGRectGetMidY(box.boundingBox)),@"width":@(box.boundingBox.size.width),@"height":@(box.boundingBox.size.height),@"context":text.string,@"confidence":@(text.confidence)}];
  }
 }
 NSData *json=[NSJSONSerialization dataWithJSONObject:items options:0 error:nil];
 puts([[NSString alloc] initWithData:json encoding:NSUTF8StringEncoding].UTF8String);
} return 0; }
