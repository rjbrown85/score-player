#import <Foundation/Foundation.h>
#import <Vision/Vision.h>
#import <ImageIO/ImageIO.h>
int main(int argc,const char *argv[]){@autoreleasepool{
 if(argc<2)return 1;
 CGImageSourceRef source=CGImageSourceCreateWithURL((__bridge CFURLRef)[NSURL fileURLWithPath:@(argv[1])],NULL);
 if(!source)return 2;CGImageRef image=CGImageSourceCreateImageAtIndex(source,0,NULL);
 NSMutableArray *results=[NSMutableArray array];int cols=(int)CGImageGetWidth(image)/160,rows=(int)CGImageGetHeight(image)/120;
 for(int row=0;row<rows;row++)for(int col=0;col<cols;col++){@autoreleasepool{
  CGImageRef tile=CGImageCreateWithImageInRect(image,CGRectMake(col*160,row*120,160,120));
  VNRecognizeTextRequest *request=[[VNRecognizeTextRequest alloc]init];request.recognitionLevel=VNRequestTextRecognitionLevelAccurate;request.usesLanguageCorrection=NO;request.recognitionLanguages=@[@"en-US"];
  VNImageRequestHandler *handler=[[VNImageRequestHandler alloc]initWithCGImage:tile options:@{}];NSError *error=nil;
  if([handler performRequests:@[request] error:&error])for(VNRecognizedTextObservation *obs in request.results){VNRecognizedText *text=[[obs topCandidates:1]firstObject];[results addObject:@{@"tile":@(row*cols+col),@"text":text.string,@"confidence":@(text.confidence)}];}
  CGImageRelease(tile);
 }}
 NSData *json=[NSJSONSerialization dataWithJSONObject:results options:0 error:nil];puts([[NSString alloc]initWithData:json encoding:NSUTF8StringEncoding].UTF8String);CGImageRelease(image);CFRelease(source);
}return 0;}
