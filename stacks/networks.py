from aws_cdk import core
import aws_cdk.aws_ec2 as ec2
import aws_cdk.aws_route53 as r53
import aws_cdk.aws_route53_targets as target


class Network(core.Stack):

    def __init__(self, scope: core.Construct, id: str, cidr_range: str, tgw_stack: core.Stack, has_endpoints: bool, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)

        current_region=kwargs['env']['region']

        # VPC Creation
        self.vpc = ec2.Vpc(self, id=f"{current_region}-vpc",
            max_azs=1,
            cidr=cidr_range,
            # configuration will create 1 subnet in a single AZ.
            subnet_configuration=[ec2.SubnetConfiguration(
                    subnet_type=ec2.SubnetType.ISOLATED,
                    name="Isolated",
                    cidr_mask=25
                    )
            ]
        )

        # Transit Gateway attachment to the VPC
        self.tgw_attachment = ec2.CfnTransitGatewayAttachment(self, id=f"tgw-vpc-{current_region}",
            transit_gateway_id=tgw_stack.tgw.ref,
            vpc_id=self.vpc.vpc_id,
            subnet_ids=[subnet.subnet_id for subnet in self.vpc.isolated_subnets],
            tags=[core.CfnTag(key='Name', value=f"tgw-{self.vpc.vpc_id}-attachment")]
        )

        # TGW Route Set the default route on the subnets to the TGW
        for subnet in self.vpc.isolated_subnets:
            ec2.CfnRoute(self, id=f"routeToTgw",
                route_table_id=subnet.route_table.route_table_id,
                destination_cidr_block='0.0.0.0/0',
                transit_gateway_id=tgw_stack.tgw.ref
            )

        self.private_host_zones=[]
        if has_endpoints:
            services = ["ssm", "ssmmessages", "ec2messages", "sqs"]
            for service in services:
                # R53 Private Host Zone
                private_host_zone=r53.PrivateHostedZone(self, id=f"{service}-private-host-zone",
                    vpc=self.vpc,
                    zone_name=f"{service}.{current_region}.amazonaws.com"
                )

                self.private_host_zones.append(private_host_zone)

                # VPC Endpoint creation
                endpoint=ec2.InterfaceVpcEndpoint(self, id=f"VPCe - {service}",
                    service=ec2.InterfaceVpcEndpointService(
                        core.Fn.sub(f"com.amazonaws.{current_region}.{service}")
                    ),
                    private_dns_enabled=False,
                    vpc=self.vpc
                )

                r53.ARecord(self, id=f"{service}-alias-record",
                    zone=private_host_zone,
                    target=r53.RecordTarget.from_alias(target.InterfaceVpcEndpointTarget(endpoint))
                )

