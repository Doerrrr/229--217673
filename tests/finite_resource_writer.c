#define _POSIX_C_SOURCE 200809L
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

/* Closed-form witness ONLY for three named shapes. Does not parse any VCF or
 * implement publication/CAS. Independently verifiable fixed field values. */
static const char *alts_long="C,G,T,AA";
static const char *alts_wide="C,G,T,AA,AC,AG,AT,ACC,ACG,ACT,AGC,AGG,AGT,ATC,ATG,ATT";
static const char *json_long="\"C\",\"G\",\"T\",\"AA\"";
static const char *json_wide="\"C\",\"G\",\"T\",\"AA\",\"AC\",\"AG\",\"AT\",\"ACC\",\"ACG\",\"ACT\",\"AGC\",\"AGG\",\"AGT\",\"ATC\",\"ATG\",\"ATT\"";
static const char *tags="\"GT\",\"AD\",\"PL\",\"DP\",\"GQ\",\"PS\"";
static void fail(void){perror("finite resource witness");exit(125);}
static FILE *open_file(const char *root,const char *name){
    char path[4096];if(snprintf(path,sizeof(path),"%s/%s",root,name)>=(int)sizeof(path))exit(125);
    FILE *f=fopen(path,"wb");if(!f)fail();return f;
}
static void close_file(FILE *f){if(ferror(f)||fclose(f))fail();}
static void fields(FILE *f,int wide,int json){
    if(json)fprintf(f,"{\"GT\":\"%s\",\"AD\":[",wide?"0|1|2|16":"0|1|2|4");
    else fprintf(f,"%s:",wide?"0|1|2|16":"0|1|2|4");
    int ad[]={1,128,40000,60000,2147483000};
    for(int i=0;i<(wide?17:5);++i)fprintf(f,"%s%d",i?",":"",wide?i+1:ad[i]);
    fputs(json?"],\"PL\":[":":",f);
    for(int i=0;i<(wide?4845:70);++i)fprintf(f,"%s%d",i?",":"",(wide?2147470000:100000)+i);
    fprintf(f,json?"],\"DP\":%d,\"GQ\":99,\"PS\":123456}":":%d:99:123456",wide?40000:200000);
}
static char *render_fields(int wide,int json){
    char *buffer=NULL;size_t length=0;FILE *f=open_memstream(&buffer,&length);if(!f)fail();
    fields(f,wide,json);close_file(f);return buffer;
}
static void name(FILE *f,int i,int wide){if(wide)fprintf(f,"S%02d",i);else fputs("S",f);}
static void source_name(FILE *f,int i,int wide){if(wide)fprintf(f,"source%02d",i);else fputs("primary",f);}
static void observation(FILE *f,int source,int ordinal,int wide,const char *value){
    fputs("{\"source\":\"",f);source_name(f,source,wide);
    fprintf(f,"\",\"ordinal\":%d,\"format\":[%s],\"values\":%s}",ordinal,tags,value);
}
int main(int argc,char **argv){
    if(argc<3||argc>4)return 125;
    int wide=!strcmp(argv[1],"wide");
    int count=wide?2:!strcmp(argv[1],"long400")?400000:!strcmp(argv[1],"long800")?800000:0;
    if(!count)return 125;
    int sources=wide?16:1,samples=wide?64:1;
    char *allocated=NULL;
    if(argc==4){
        if(strcmp(argv[3],"linear"))return 125;
        size_t size=(size_t)count*200;allocated=malloc(size);if(!allocated)fail();
        volatile char *touch=allocated;
        for(size_t i=0;i<size;i+=4096)touch[i]=1;
    }
    char *j=render_fields(wide,1),*v=render_fields(wide,0);
    const char *alts=wide?alts_wide:alts_long,*dict=wide?json_wide:json_long;
    for(int s=0;s<sources;++s){
        char path[64];snprintf(path,sizeof(path),"source%02d.vcf",s);FILE *f=open_file(argv[2],path);
        fputs("##fileformat=VCFv4.3\n##contig=<ID=chr7,length=2000000>\n",f);
        fputs("##FORMAT=<ID=GT,Number=1,Type=String,Description=\"GT\">\n",f);
        fputs("##FORMAT=<ID=AD,Number=R,Type=Integer,Description=\"AD\">\n",f);
        fputs("##FORMAT=<ID=PL,Number=G,Type=Integer,Description=\"PL\">\n",f);
        fputs("##FORMAT=<ID=DP,Number=1,Type=Integer,Description=\"DP\">\n",f);
        fputs("##FORMAT=<ID=GQ,Number=1,Type=Integer,Description=\"GQ\">\n",f);
        fputs("##FORMAT=<ID=PS,Number=1,Type=Integer,Description=\"PS\">\n",f);
        fputs("#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tFORMAT",f);
        for(int i=0;i<samples;++i){fputc('\t',f);name(f,i,wide);}fputc('\n',f);
        for(int r=0;r<count;++r){
            fprintf(f,"chr7\t%d\t.\tA\t%s\t.\tPASS\t.\tGT:AD:PL:DP:GQ:PS",wide?31:count-r,alts);
            for(int i=0;i<samples;++i){fputc('\t',f);fputs(v,f);}fputc('\n',f);
        }close_file(f);
    }
    FILE *f=open_file(argv[2],"release.jsonl");
    for(int r=0;r<(wide?1:count);++r){
        fprintf(f,"{\"chrom\":\"chr7\",\"position\":%d,\"reference\":\"A\",\"alternate\":[%s],\"contributors\":[",wide?31:r+1,dict);
        for(int s=0;s<sources;++s)for(int k=0;k<(wide?2:1);++k){
            if(s||k)fputc(',',f);
            fputs("{\"source\":\"",f);source_name(f,s,wide);
            fprintf(f,"\",\"ordinal\":%d}",wide?k:count-r-1);
        }fputs("],\"samples\":[",f);
        for(int i=0;i<samples;++i){
            if(i)fputc(',',f);
            fputs("{\"name\":\"",f);name(f,i,wide);fputs("\",\"winner\":",f);
            observation(f,0,wide?0:count-r-1,wide,j);fputs(",\"others\":[",f);
            for(int s=0;s<sources;++s)for(int k=0;k<(wide?2:1);++k){
                if(!s&&!k)continue;
                if(s!=0||k!=1)fputc(',',f);
                observation(f,s,k,wide,j);
            }fputs("]}",f);
        }fputs("]}\n",f);
    }close_file(f);
    f=open_file(argv[2],"original.jsonl");
    for(int s=0;s<sources;++s)for(int r=0;r<count;++r){
        fputs("{\"source\":\"",f);source_name(f,s,wide);
        fprintf(f,"\",\"ordinal\":%d,\"chrom\":\"chr7\",\"position\":%d,\"reference\":\"A\",\"alternate\":[%s],\"format\":[%s],\"samples\":[",r,wide?31:count-r,dict,tags);
        for(int i=0;i<samples;++i){
            if(i)fputc(',',f);
            fputs("{\"name\":\"",f);name(f,i,wide);fprintf(f,"\",\"values\":%s}",j);
        }fputs("]}\n",f);
    }close_file(f);free(j);free(v);free(allocated);return 0;
}
